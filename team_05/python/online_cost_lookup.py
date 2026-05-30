"""
online_cost_lookup.py
---------------------
Resolve cost rates for rooms / doors / windows / columns / finishes.

Lookup order:
    1) cost_rates.json (local, authoritative)
    2) online_cost_cache.json (previously fetched online rates)
    3) OpenCost API (opencost_database.OpenCostDatabase)
    4) Web search fallback (DuckDuckGo HTML scrape)
    5) Category default from cost_rates.json
    6) Hard-coded final fallback

Usage
-----
    from online_cost_lookup import CostResolver

    resolver = CostResolver()                       # auto-finds cost_rates.json
    rate = resolver.get_finish_rate("floor_finish", "bamboo")
    rate = resolver.get_element_rate("doors", subtype="sliding", item_id=None)

CLI
---
    python online_cost_lookup.py floor_finish bamboo
    python online_cost_lookup.py doors --subtype sliding
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

try:
    import requests
except ImportError:
    requests = None  # online lookup will be disabled

try:
    from opencost_database import OpenCostDatabase
except Exception:  # pragma: no cover - optional dependency
    OpenCostDatabase = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(key: str) -> str:
    """Lowercase, collapse separators ('-' / '_' / spaces) -> '_'."""
    if key is None:
        return ""
    return re.sub(r"[\s\-]+", "_", str(key).strip().lower())


def _find_default_json() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "gh" / "cost_rates.json",
        here.parent / "cost_rates.json",
        Path.cwd() / "cost_rates.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "cost_rates.json not found. Pass json_path explicitly to CostResolver()."
    )


# ---------------------------------------------------------------------------
# Online fetcher
# ---------------------------------------------------------------------------

class OnlineCostFetcher:
    """
    Best-effort online fetcher for construction cost rates.

    Primary source : OpenCost API (via opencost_database.OpenCostDatabase).
    Fallback       : DuckDuckGo HTML search + regex extraction of AED/m2 values.

    Both sources are heuristic - treat results as estimates. Override
    `fetch()` or supply a custom `opencost` instance to plug in another
    pricing service.
    """

    SEARCH_URL = "https://duckduckgo.com/html/"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    # category_key -> human phrase used in the search query
    PHRASE = {
        "floor_finish": "flooring",
        "wall_finish": "wall finish",
        "ceiling_material": "ceiling",
        "slab_material": "concrete slab",
        "door_leaf": "door",
        "door_frame": "door frame",
        "window": "window",
        "column_finish": "column finish",
        "rooms": "interior fit-out",
        "doors": "door",
        "windows": "window",
        "columns": "column",
    }

    def __init__(
        self,
        currency: str = "AED",
        region: str = "Dubai",
        timeout: float = 8.0,
        opencost: Optional[Any] = None,
        use_opencost: bool = True,
    ):
        self.currency = currency
        self.region = region
        self.timeout = timeout
        self.use_opencost = use_opencost and OpenCostDatabase is not None
        if opencost is not None:
            self.opencost = opencost
        elif self.use_opencost:
            try:
                self.opencost = OpenCostDatabase()
            except Exception as exc:
                print(f"[online] OpenCost init failed: {exc}")
                self.opencost = None
                self.use_opencost = False
        else:
            self.opencost = None

    # ------------------------------------------------------------------
    def fetch(self, category: str, material: Optional[str] = None) -> Optional[float]:
        """Return a numeric rate (currency per m2 or per element) or None."""
        # 1) Try OpenCost
        if self.use_opencost and self.opencost is not None:
            for query in self._opencost_queries(category, material):
                try:
                    rate = self.opencost.get_cost(query)
                except Exception as exc:
                    print(f"[online] OpenCost error for '{query}': {exc}")
                    rate = None
                if rate:
                    return float(rate)

        # 2) Fall back to web search scrape
        if requests is None:
            print("[online] 'requests' not installed; skipping web lookup.")
            return None

        phrase = self.PHRASE.get(category, category.replace("_", " "))
        material_part = (material or "").replace("_", " ")
        query = f"{material_part} {phrase} price {self.currency} {self.region} per m2".strip()
        try:
            resp = requests.post(
                self.SEARCH_URL,
                data={"q": query},
                headers=self.HEADERS,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                print(f"[online] HTTP {resp.status_code} for query: {query}")
                return None
            price = self.extract_price(resp.text)
            if price is not None:
                print(f"[online] {category}/{material} -> {price} {self.currency} (web est.)")
            else:
                print(f"[online] No price extracted for: {query}")
            return price
        except Exception as exc:
            print(f"[online] Web lookup failed: {exc}")
            return None

    # ------------------------------------------------------------------
    def _opencost_queries(self, category: str, material: Optional[str]) -> list[str]:
        """Build candidate item names to try against OpenCost."""
        phrase = self.PHRASE.get(category, category.replace("_", " "))
        mat = (material or "").replace("_", " ").strip()
        queries: list[str] = []
        if mat:
            queries.append(f"{mat} {phrase}".strip())
            queries.append(mat)
        queries.append(phrase)
        # de-dup, keep order
        seen, out = set(), []
        for q in queries:
            k = q.lower()
            if q and k not in seen:
                seen.add(k)
                out.append(q)
        return out

    # ------------------------------------------------------------------
    def extract_price(self, html: str) -> Optional[float]:
        """
        Pull the first plausible '<currency> N' or 'N <currency>' value from the
        search-result HTML and return its median if multiple are found.
        """
        cur = re.escape(self.currency)
        patterns = [
            rf"{cur}\s*([0-9][0-9,\.]{{1,9}})",
            rf"([0-9][0-9,\.]{{1,9}})\s*{cur}",
            rf"AED\s*([0-9][0-9,\.]{{1,9}})",
        ]
        candidates: list[float] = []
        for pat in patterns:
            for raw in re.findall(pat, html, flags=re.IGNORECASE):
                try:
                    val = float(raw.replace(",", ""))
                except ValueError:
                    continue
                # Filter implausible values for AED/m2 construction rates
                if 20 <= val <= 20000:
                    candidates.append(val)
        if not candidates:
            return None
        candidates.sort()
        return candidates[len(candidates) // 2]


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class CostResolver:
    FINISH_GROUPS = {
        "floor_finish": ("room_finishes", "floor_finish"),
        "wall_finish": ("room_finishes", "wall_finish"),
        "ceiling_material": ("room_finishes", "ceiling_material"),
        "slab_material": ("room_finishes", "slab_material"),
        "door_leaf": ("door_finishes", "leaf_material"),
        "door_frame": ("door_finishes", "frame_material"),
        "window": ("window_finishes", None),
        "column_finish": ("column_finishes", None),
    }

    HARD_FALLBACK = 1000.0  # last-resort numeric

    def __init__(
        self,
        json_path: Optional[str | Path] = None,
        cache_path: Optional[str | Path] = None,
        fetcher: Optional[OnlineCostFetcher] = None,
        enable_online: bool = True,
    ):
        self.json_path = Path(json_path) if json_path else _find_default_json()
        self.cache_path = Path(cache_path) if cache_path else (
            self.json_path.parent / "online_cost_cache.json"
        )
        self.data = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.cache = self._load_cache()
        self.fetcher = fetcher or OnlineCostFetcher()
        self.enable_online = enable_online

    # ------------------------------------------------------------------
    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_cache(self) -> None:
        self.cache_path.write_text(
            json.dumps(self.cache, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _cache_key(self, category: str, material: Optional[str]) -> str:
        return f"{_normalize(category)}::{_normalize(material) or '_default'}"

    # ------------------------------------------------------------------
    # Finish (per-m2) lookup
    # ------------------------------------------------------------------
    def get_finish_rate(self, category: str, material: Optional[str]) -> float:
        """
        Resolve a per-m2 rate for a finish/material category.
        category: one of FINISH_GROUPS keys
        material: user-text material name (case/separator insensitive)
        """
        if category not in self.FINISH_GROUPS:
            raise KeyError(f"Unknown finish category: {category}")

        # 1) Local JSON
        local = self._lookup_local_finish(category, material)
        if local is not None:
            return float(local)

        # 2) Cache
        ck = self._cache_key(category, material)
        if ck in self.cache:
            return float(self.cache[ck]["rate"])

        # 3) Online
        if self.enable_online and material:
            rate = self.fetcher.fetch(category, material)
            if rate is not None:
                self.cache[ck] = {
                    "rate": rate,
                    "source": "online",
                    "ts": int(time.time()),
                }
                self._save_cache()
                return float(rate)

        # 4) Local default for the category
        default = self._lookup_local_finish(category, None)
        if default is not None:
            return float(default)

        # 5) Hard fallback
        return self.HARD_FALLBACK

    def _lookup_local_finish(
        self, category: str, material: Optional[str]
    ) -> Optional[float]:
        group, sub = self.FINISH_GROUPS[category]
        node = self.data.get(group, {})
        if sub:
            node = node.get(sub, {})

        if material:
            mkey = _normalize(material)
            by_mat = node.get("by_material", {})
            for k, v in by_mat.items():
                if _normalize(k) == mkey:
                    return v
            return None  # material specified but not found
        return node.get("default")

    # ------------------------------------------------------------------
    # Element (rooms/doors/windows/columns) lookup
    # ------------------------------------------------------------------
    def get_element_rate(
        self,
        category: str,            # "rooms" | "doors" | "windows" | "columns"
        item_id: Optional[str] = None,
        subtype: Optional[str] = None,
    ) -> float:
        node = self.data.get(category)
        if node is None:
            raise KeyError(f"Unknown element category: {category}")

        # by_id
        if item_id:
            for k, v in node.get("by_id", {}).items():
                if _normalize(k) == _normalize(item_id):
                    return float(v)

        # by_subtype / by_category
        sub_map = node.get("by_subtype") or node.get("by_category") or {}
        if subtype:
            for k, v in sub_map.items():
                if _normalize(k) == _normalize(subtype):
                    return float(v)

        # cache + online (use subtype or item_id as the "material")
        material = subtype or item_id
        ck = self._cache_key(category, material)
        if ck in self.cache:
            return float(self.cache[ck]["rate"])

        if self.enable_online and material:
            rate = self.fetcher.fetch(category, material)
            if rate is not None:
                self.cache[ck] = {
                    "rate": rate,
                    "source": "online",
                    "ts": int(time.time()),
                }
                self._save_cache()
                return float(rate)

        return float(node.get("default", self.HARD_FALLBACK))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    p = argparse.ArgumentParser(description="Resolve a cost rate.")
    p.add_argument("category", help="e.g. floor_finish, wall_finish, doors, windows")
    p.add_argument("material", nargs="?", default=None,
                   help="Material name (for finishes)")
    p.add_argument("--subtype", default=None, help="Element subtype")
    p.add_argument("--id", dest="item_id", default=None, help="Element id")
    p.add_argument("--no-online", action="store_true", help="Disable online lookup")
    p.add_argument("--json", dest="json_path", default=None, help="Path to cost_rates.json")
    args = p.parse_args()

    r = CostResolver(json_path=args.json_path, enable_online=not args.no_online)

    if args.category in CostResolver.FINISH_GROUPS:
        rate = r.get_finish_rate(args.category, args.material)
    else:
        rate = r.get_element_rate(args.category, item_id=args.item_id, subtype=args.subtype)

    print(f"{args.category} / {args.material or args.subtype or args.item_id or 'default'} = {rate}")


if __name__ == "__main__":
    _main()
