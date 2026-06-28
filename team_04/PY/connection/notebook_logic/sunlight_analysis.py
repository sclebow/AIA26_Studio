"""Sunlight and daylight analysis for site optimization.

Provides functions to:
- Calculate sun position (altitude, azimuth) for given location and time
- Analyze building exposure to sunlight
- Score daylight quality
- Estimate seasonal sun exposure
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, NamedTuple

from shapely.geometry import Point, Polygon


# ============================================================================
# Sun Data Structures
# ============================================================================

class SunPosition(NamedTuple):
    """Sun position in sky."""
    altitude: float  # degrees above horizon (-90 to 90)
    azimuth: float   # degrees from north, clockwise (0-360)
    elevation: float  # radians for calculations


class SunData(NamedTuple):
    """Sun data for a location and date."""
    latitude: float
    longitude: float
    date: datetime
    sunrise: datetime
    sunset: datetime
    sun_noon: datetime
    day_length_hours: float


# ============================================================================
# Sun Position Calculation (NOAA Solar Calculator simplified)
# ============================================================================

def julian_day(date: datetime) -> float:
    """Calculate Julian day number for a given date."""
    a = (14 - date.month) // 12
    y = date.year + 4800 - a
    m = date.month + 12 * a - 3
    jdn = date.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn + (date.hour - 12) / 24.0


def equation_of_time(jd: float) -> float:
    """Calculate equation of time (minutes)."""
    t = (jd - 2451545.0) / 36525.0
    epsilon = 23.439291 - 0.0130042 * t
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    e = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t

    epsilon_rad = math.radians(epsilon)
    l0_rad = math.radians(l0)
    m_rad = math.radians(m)

    y = math.tan(epsilon_rad / 2)
    y2 = y * y

    eq_time = 4 * (
        y2 * math.sin(2 * l0_rad)
        - 2 * e * math.sin(m_rad)
        + 4 * e * y2 * math.sin(m_rad) * math.cos(2 * l0_rad)
        - 0.5 * y2 * y2 * math.sin(4 * l0_rad)
        - 1.25 * e * e * math.sin(2 * m_rad)
    )

    return math.degrees(eq_time) * 4


def solar_declination(jd: float) -> float:
    """Calculate solar declination (degrees)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t
    m = 357.52911 + 35999.05029 * t
    l0_rad = math.radians(l0)
    m_rad = math.radians(m)

    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000029 * math.sin(3 * m_rad)
    )

    sun_lon_rad = math.radians(l0 + c)
    epsilon = 23.43929 - 0.0130042 * t
    epsilon_rad = math.radians(epsilon)

    declination = math.degrees(math.asin(math.sin(epsilon_rad) * math.sin(sun_lon_rad)))
    return declination


def calculate_sun_position(
    latitude: float,
    longitude: float,
    date: datetime,
) -> tuple[SunPosition, dict[str, Any]]:
    """Calculate sun position (altitude and azimuth) for a given location and time.

    Args:
        latitude: Site latitude (degrees, positive north)
        longitude: Site longitude (degrees, positive east)
        date: Date and time (should be in UTC)

    Returns:
        (SunPosition, metadata dict)
    """
    jd = julian_day(date)
    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)

    # Solar declination
    declination = solar_declination(jd)
    decl_rad = math.radians(declination)

    # Equation of time
    eq_time = equation_of_time(jd)

    # Local solar time
    lst = date.hour + date.minute / 60 + date.second / 3600
    lst += (eq_time / 60) + (longitude / 15)

    # Hour angle
    hour_angle = (lst - 12) * 15
    ha_rad = math.radians(hour_angle)

    # Altitude (elevation angle)
    sin_alt = math.sin(lat_rad) * math.sin(decl_rad) + math.cos(lat_rad) * math.cos(
        decl_rad
    ) * math.cos(ha_rad)
    altitude = math.degrees(math.asin(sin_alt))

    # Azimuth
    cos_az = (math.sin(decl_rad) - math.sin(lat_rad) * sin_alt) / (
        math.cos(lat_rad) * math.cos(math.asin(sin_alt))
    )
    azimuth = hour_angle + math.degrees(
        math.acos(max(-1, min(1, cos_az)))
    )  # Clamp for numerical stability
    if hour_angle > 0:
        azimuth = 360 - azimuth

    return (
        SunPosition(
            altitude=altitude,
            azimuth=azimuth % 360,
            elevation=math.radians(altitude),
        ),
        {
            "declination": declination,
            "equation_of_time": eq_time,
            "hour_angle": hour_angle,
            "julian_day": jd,
        },
    )


def calculate_sunrise_sunset(
    latitude: float,
    longitude: float,
    date: datetime,
) -> tuple[datetime, datetime, datetime]:
    """Calculate sunrise, sunset, and solar noon for a given date and location.

    Args:
        latitude: Site latitude (degrees)
        longitude: Site longitude (degrees)
        date: Date (time portion ignored)

    Returns:
        (sunrise, sunset, solar_noon) as datetime objects
    """
    jd = julian_day(datetime(date.year, date.month, date.day, 12, 0, 0))
    lat_rad = math.radians(latitude)

    # Solar declination
    declination = solar_declination(jd)
    decl_rad = math.radians(declination)

    # Hour angle at sunrise/sunset (altitude = 0)
    cos_ha = -math.tan(lat_rad) * math.tan(decl_rad)
    cos_ha = max(-1, min(1, cos_ha))  # Clamp

    ha_sunrise = -math.degrees(math.acos(cos_ha))
    ha_sunset = math.degrees(math.acos(cos_ha))

    eq_time = equation_of_time(jd)

    sunrise_hour = 12 + ha_sunrise / 15 - eq_time / 60 - longitude / 15
    sunset_hour = 12 + ha_sunset / 15 - eq_time / 60 - longitude / 15
    noon_hour = 12 - eq_time / 60 - longitude / 15

    # Convert to datetime
    base_date = date.replace(hour=0, minute=0, second=0, microsecond=0)

    sunrise = base_date + timedelta(hours=sunrise_hour)
    sunset = base_date + timedelta(hours=sunset_hour)
    solar_noon = base_date + timedelta(hours=noon_hour)

    return sunrise, sunset, solar_noon


def get_sun_data(
    latitude: float,
    longitude: float,
    date: datetime | None = None,
) -> SunData:
    """Get comprehensive sun data for a location and date.

    Args:
        latitude: Site latitude
        longitude: Site longitude
        date: Date (defaults to today)

    Returns:
        SunData with sunrise, sunset, day length
    """
    if date is None:
        date = datetime.now()

    sunrise, sunset, solar_noon = calculate_sunrise_sunset(latitude, longitude, date)
    day_length = (sunset - sunrise).total_seconds() / 3600

    return SunData(
        latitude=latitude,
        longitude=longitude,
        date=date,
        sunrise=sunrise,
        sunset=sunset,
        sun_noon=solar_noon,
        day_length_hours=day_length,
    )


# ============================================================================
# Sunlight Exposure Analysis
# ============================================================================

def calculate_facade_exposure(
    building_footprint: list[list[float]],
    sun_position: SunPosition,
    facade_normal: float,  # degrees from north
) -> float:
    """Calculate how much a facade is exposed to direct sunlight.

    Args:
        building_footprint: Building perimeter
        sun_position: Sun position in sky
        facade_normal: Direction the facade faces (degrees from north)

    Returns:
        Exposure score (0-1, where 1 is full sun exposure)
    """
    if sun_position.altitude < 0:
        return 0.0  # Sun below horizon

    # Angle between sun azimuth and facade normal
    sun_az = sun_position.azimuth
    angle_diff = abs(sun_az - facade_normal)

    # Normalize to 0-180
    if angle_diff > 180:
        angle_diff = 360 - angle_diff

    # Cosine-weighted exposure (perpendicular = 1.0)
    cos_angle = math.cos(math.radians(angle_diff))
    exposure = max(0, cos_angle)

    # Weight by solar altitude (lower sun = weaker)
    altitude_factor = math.sin(sun_position.elevation)
    altitude_factor = max(0, altitude_factor)

    return exposure * altitude_factor


def calculate_sun_exposure(
    building_footprint: list[list[float]],
    site_boundary: list[list[float]],
    sun_data: SunData,
    sample_hours: int = 8,  # Sample sun position at intervals
) -> dict[str, Any]:
    """Analyze sun exposure of a building on a given date.

    Args:
        building_footprint: Building coordinates
        site_boundary: Site coordinates (for open space calculation)
        sun_data: Sun data for the location
        sample_hours: Number of hourly samples during daylight

    Returns:
        Exposure metrics dict
    """
    sunrise = sun_data.sunrise
    sunset = sun_data.sunset
    day_length = sun_data.day_length_hours

    if day_length <= 0:
        return {
            "exposure_score": 0.0,
            "mean_altitude": 0.0,
            "mean_azimuth": 0.0,
            "peak_altitude": 0.0,
            "message": "No daylight on this date",
        }

    # Sample sun position at regular intervals
    altitudes = []
    azimuths = []

    for i in range(sample_hours):
        hour_offset = (i / sample_hours) * day_length
        sample_time = sunrise + timedelta(hours=hour_offset)

        sun_pos, _ = calculate_sun_position(sun_data.latitude, sun_data.longitude, sample_time)
        altitudes.append(sun_pos.altitude)
        azimuths.append(sun_pos.azimuth)

    mean_altitude = sum(altitudes) / len(altitudes) if altitudes else 0
    mean_azimuth = sum(azimuths) / len(azimuths) if azimuths else 0
    peak_altitude = max(altitudes) if altitudes else 0

    # Calculate building centroid for orientation
    centroid_x = sum(p[0] for p in building_footprint) / len(building_footprint)
    centroid_y = sum(p[1] for p in building_footprint) / len(building_footprint)

    # Find longest edge as main facade
    longest_edge_length = 0
    longest_facade_normal = 0

    for i in range(len(building_footprint)):
        p1 = building_footprint[i]
        p2 = building_footprint[(i + 1) % len(building_footprint)]

        edge_dx = p2[0] - p1[0]
        edge_dy = p2[1] - p1[1]
        edge_length = math.sqrt(edge_dx**2 + edge_dy**2)

        if edge_length > longest_edge_length:
            longest_edge_length = edge_length
            # Normal to edge points outward
            normal_angle = math.atan2(edge_dx, edge_dy)
            longest_facade_normal = math.degrees(normal_angle)

    # Calculate mean exposure across sampled hours
    mean_exposure = 0.0
    for i, altitude in enumerate(altitudes):
        sun_pos = SunPosition(
            altitude=altitude,
            azimuth=azimuths[i],
            elevation=math.radians(altitude),
        )
        exposure = calculate_facade_exposure(building_footprint, sun_pos, longest_facade_normal)
        mean_exposure += exposure

    mean_exposure = (mean_exposure / len(altitudes) * 100) if altitudes else 0

    return {
        "exposure_score": mean_exposure,
        "mean_altitude": mean_altitude,
        "mean_azimuth": mean_azimuth,
        "peak_altitude": peak_altitude,
        "day_length_hours": day_length,
        "longest_facade_orientation": longest_facade_normal,
        "message": f"Exposure: {mean_exposure:.1f}%, Peak sun: {peak_altitude:.1f}°",
    }


def score_daylight(
    building_footprint: list[list[float]],
    site_boundary: list[list[float]],
    sun_data: SunData | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> float:
    """Score the daylight quality of a building location (0-100).

    Considers:
    - Building orientation relative to sun
    - Peak solar altitude
    - Day length
    - Open space access

    Args:
        building_footprint: Building coordinates
        site_boundary: Site coordinates
        sun_data: Precomputed sun data (if None, will be calculated)
        latitude: Site latitude (required if sun_data is None)
        longitude: Site longitude (required if sun_data is None)

    Returns:
        Daylight score 0-100
    """
    if sun_data is None:
        if latitude is None or longitude is None:
            return 50.0  # Default if no location data

        sun_data = get_sun_data(latitude, longitude)

    exposure = calculate_sun_exposure(building_footprint, site_boundary, sun_data)
    exposure_score = exposure.get("exposure_score", 0)

    # Weight by day length (longer days = better)
    day_length_factor = min(1.0, sun_data.day_length_hours / 12)

    # Combine scores
    daylight_score = exposure_score * 0.6 + (day_length_factor * 100) * 0.4

    # Clamp to 0-100
    return max(0, min(100, daylight_score))


def calculate_seasonal_exposure(
    building_footprint: list[list[float]],
    site_boundary: list[list[float]],
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Calculate sun exposure for key seasonal dates.

    Args:
        building_footprint: Building coordinates
        site_boundary: Site coordinates
        latitude: Site latitude
        longitude: Site longitude

    Returns:
        Seasonal exposure metrics
    """
    today = datetime.now()
    year = today.year

    seasonal_dates = {
        "winter_solstice": datetime(year, 12, 21),
        "spring_equinox": datetime(year, 3, 20),
        "summer_solstice": datetime(year, 6, 21),
        "autumn_equinox": datetime(year, 9, 22),
    }

    seasonal_scores = {}

    for season, date in seasonal_dates.items():
        sun_data = get_sun_data(latitude, longitude, date)
        exposure = calculate_sun_exposure(building_footprint, site_boundary, sun_data)
        seasonal_scores[season] = {
            "date": date.strftime("%Y-%m-%d"),
            "exposure_score": exposure.get("exposure_score", 0),
            "day_length_hours": sun_data.day_length_hours,
            "peak_altitude": exposure.get("peak_altitude", 0),
        }

    mean_exposure = sum(s["exposure_score"] for s in seasonal_scores.values()) / len(
        seasonal_scores
    )

    return {
        "seasonal_exposure": seasonal_scores,
        "mean_seasonal_exposure": mean_exposure,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }
