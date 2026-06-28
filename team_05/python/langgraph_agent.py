"""
LangGraph Agent Orchestration Layer
Routes user input to Python Copilot or Swiftlet MCP tools.
After a finish-change request, stores an updated layout for the caller to use.
"""
import json

from python_copilot import apply_finish_to_layout, process_with_copilot
from swiftlet_mcp import process_with_swiftlet, push_layout_to_grasshopper


class LangGraphAgent:
    def __init__(self) -> None:
        self._updated_layout: dict | None = None

    def process(
        self,
        user_input: str,
        layout: dict | None = None,
        plans: dict[str, dict] | None = None,
        active_plan_key: str | None = None,
        history: list[dict] | None = None,
        client_profile: dict | None = None,
    ) -> str:
        """Route input to the appropriate backend and return the response text."""
        self._updated_layout = None  # reset on each call

        resolved_input = self._resolve_followup_input(user_input, history)

        context = self._build_context(resolved_input, layout, plans, active_plan_key, history, client_profile)

        if self._should_compare_plans(resolved_input, plans) and plans:
            response = self._compare_plans(resolved_input, plans, active_plan_key)
            return response

        if self._should_use_copilot(resolved_input):
            response = process_with_copilot(context)
            # if this was a finish-change, produce the updated layout and push to GH
            if layout is not None:
                updated = apply_finish_to_layout(resolved_input, layout)
                if updated is not None:
                    self._updated_layout = updated
                    self._push_to_grasshopper(resolved_input, updated)
        else:
            response = process_with_swiftlet(context)

        return response

    def get_updated_layout(self) -> dict | None:
        """
        Returns the layout with recalculated costs and colors after a finish change,
        or None if the last call did not modify the layout.
        """
        return self._updated_layout

    def _push_to_grasshopper(self, user_input: str, updated_layout: dict) -> None:
        """
        Push the updated layout to GH and adopt GH's returned layout as
        authoritative so the GUI floor plan shows the same colors as GH.
        GH returns the same room IDs as we sent, so id-based merge works.
        """
        try:
            from python_copilot import _find_room
            rooms = updated_layout.get("rooms", [])
            room = _find_room(user_input.lower(), rooms)
            room_name = room.get("name") if room else None
            result = push_layout_to_grasshopper(updated_layout, room_name)
            if result["ok"]:
                print(f"[GH] Layout pushed via {result['tool']} for room '{room_name}'")
                if result.get("gh_layout"):
                    self._updated_layout = result["gh_layout"]
                    print("[GH] Adopted GH colors — GUI heatmap will match GH")
            else:
                print(f"[GH] Push failed: {result['error']}")
        except Exception as e:
            print(f"[GH] Push skipped: {e}")

    # ── private helpers ───────────────────────────────────────────────────────

    def _should_use_copilot(self, user_input: str) -> bool:
        keywords = (
            "local", "cost", "area", "rate", "room", "total", "budget",
            "price", "cheap", "expensive", "compare", "heatmap", "calculate",
            "finish", "floor", "wall", "ceiling", "marble", "tile", "wood",
            "reduce", "save",
            "slab", "thickness", "rc_solid", "rc_waffle", "rc_ribbed",
            "post_tensioned", "hollow_core", "composite_steel", "precast",
            "timber_joist", "mm", " m ",
        )
        lower = user_input.lower()
        return any(k in lower for k in keywords)

    def _resolve_followup_input(self, user_input: str, history: list[dict] | None) -> str:
        """
        Convert one-word follow-ups like "all" into a full finish-change command
        by reusing the latest user finish-change request from chat history.
        """
        text = (user_input or "").strip()
        lower = text.lower()
        ack_words = {"ok", "okay", "yes", "y", "sure", "go ahead", "continue"}

        # If user acknowledges after a clarification error, replay the latest actionable user command
        # instead of routing to MCP with a generic "ok".
        if lower in ack_words and history:
            saw_target_prompt = False
            for msg in reversed(history):
                role = msg.get("role")
                content = (msg.get("content") or "").strip()
                content_low = content.lower()
                if role == "assistant" and ("need the room target" in content_low or "need a room target" in content_low):
                    saw_target_prompt = True
                    continue
                if saw_target_prompt and role == "user" and content:
                    return content

        is_all_followup = lower in {"all", "all rooms", "all spaces"} or lower.startswith("all ")
        if not is_all_followup:
            return text
        if not history:
            return text

        for msg in reversed(history):
            if msg.get("role") != "user":
                continue
            prev = (msg.get("content") or "").strip()
            prev_low = prev.lower()

            # Area-change follow-up (e.g. previous: "increase living room area by 10%", now: "all living room").
            if ("area" in prev_low or "m2" in prev_low or "m²" in prev_low or "sqm" in prev_low) and any(
                k in prev_low for k in ("increase", "decrease", "reduce", "shrink", "expand", "larger", "smaller", "%")
            ):
                return f"{prev} for {text}"

            if ("floor" in prev_low or "wall" in prev_low or "ceiling" in prev_low) and any(
                m in prev_low for m in ("marble", "granite", "porcelain", "ceramic", "wood", "carpet", "vinyl", "epoxy", "tile")
            ):
                return f"{prev} for {text}"
        return text

    def _should_compare_plans(self, user_input: str, plans: dict[str, dict] | None = None) -> bool:
        lower = user_input.lower()
        # hard keywords that always mean multi-plan regardless of how many are loaded
        hard_keywords = (
            "compare plans", "plan comparison", "comparison",
            "total-cost comparison", "total cost comparison",
            "all plans", "each plan", "five plans", "plans total",
            "plan totals", "cost for each plan",
            "which plan is cheapest", "which plan is most expensive",
            "cheapest plan", "most expensive plan",
        )
        if any(k in lower for k in hard_keywords):
            return True

        # When multiple plans are actually loaded: "plan(s)" + action word triggers comparison
        if plans and len(plans) > 1:
            import re
            has_plan_word = bool(re.search(r'\bplans?\b', lower))
            action_words = ("compare", "rank", "best", "cheapest", "expensive",
                            "which", "cost", "choose", "recommend", "value")
            if has_plan_word and any(k in lower for k in action_words):
                return True
            # also catch "X plans" where X is a digit
            if re.search(r'\d+\s+plans?\b', lower):
                return True

        return False

    def _compare_plans(self, user_input: str, plans: dict[str, dict], active_plan_key: str | None) -> str:
        _MAINT_PCT = {"wet": 0.020, "bedroom": 0.012, "common": 0.010,
                      "circulation": 0.008, "service": 0.015}

        rows = []
        for plan_name, layout in plans.items():
            proj   = layout.get("project", {})
            rooms  = layout.get("rooms", [])
            currency = proj.get("currency", "")
            totals = layout.get("totals", {})
            room_total = totals.get("rooms", sum((r.get("total_cost", 0) or 0) for r in rooms))
            grand  = totals.get("grand", room_total)
            area   = sum(r.get("area_m2", 0) for r in rooms)
            avg_rate = (grand / area) if area else 0
            maint_yr = sum(
                (r.get("total_cost", 0) or 0) * _MAINT_PCT.get(r.get("category", "").lower(), 0.012)
                for r in rooms
            )
            rows.append({
                "name": plan_name, "grand": float(grand), "currency": currency,
                "rooms": len(rooms), "area": area, "avg_rate": avg_rate, "maint_yr": maint_yr,
                "active": plan_name == active_plan_key,
            })

        if not rows:
            return "No saved plans are available for comparison yet."

        rows.sort(key=lambda r: r["grand"])
        cheapest_total = rows[0]["grand"]
        currency = rows[0]["currency"]

        active_label = f"Active plan: **{active_plan_key}**\n\n" if active_plan_key else ""
        lines = [
            active_label + "**Plan comparison — ranked by total cost:**\n",
            f"| # | Plan | Rooms | Total area m2 | Avg rate /m2 | Grand total | vs cheapest | Est. annual maintenance |",
            "|---|------|-------|--------------|-------------|-------------|------------|------------------------|",
        ]
        for i, r in enumerate(rows, 1):
            delta = r["grand"] - cheapest_total
            delta_pct = 0.0 if cheapest_total == 0 else (delta / cheapest_total) * 100.0
            marker = " *" if r["active"] else ""
            lines.append(
                f"| {i} | {r['name']}{marker} | {r['rooms']} "
                f"| {r['area']:,.1f} | {r['avg_rate']:,.0f} {currency} "
                f"| **{r['grand']:,.0f} {currency}** "
                f"| +{delta:,.0f} ({delta_pct:.1f}%) "
                f"| ~{r['maint_yr']:,.0f} {currency}/yr |"
            )

        most_exp = rows[-1]
        spread = most_exp["grand"] - cheapest_total
        spread_pct = 0.0 if cheapest_total == 0 else (spread / cheapest_total) * 100.0
        lines += [
            "",
            f"**Cheapest:** {rows[0]['name']} at {rows[0]['grand']:,.0f} {currency}",
            f"**Most expensive:** {most_exp['name']} at {most_exp['grand']:,.0f} {currency}",
            f"**Cost spread:** {spread:,.0f} {currency} ({spread_pct:.1f}%)",
            "",
            "_* = active plan | Maintenance: wet 2%/yr | bedrooms 1.2%/yr | common 1%/yr | "
            "circulation 0.8%/yr (rule-of-thumb)._",
        ]
        return "\n".join(lines)

    def _build_context(
        self,
        user_input: str,
        layout: dict | None,
        plans: dict[str, dict] | None,
        active_plan_key: str | None,
        history: list[dict] | None,
        client_profile: dict | None = None,
    ) -> dict:
        ctx: dict = {"user_input": user_input}
        if layout:
            ctx["layout_summary"] = self._summarise_layout(layout)
            ctx["layout_json"] = json.dumps(layout)
        if plans:
            ctx["plans"] = plans
            if active_plan_key and active_plan_key in plans:
                ctx["active_plan_key"] = active_plan_key
        if history:
            ctx["history"] = history[-10:]
        if client_profile:
            try:
                from client_profile import generate_summary
                ctx["client_profile_summary"] = generate_summary(client_profile)
            except Exception:
                pass
        return ctx

    @staticmethod
    def _summarise_layout(layout: dict) -> str:
        proj = layout.get("project", {})
        if isinstance(proj, str):
            proj = {"name": proj}
        rooms = layout.get("rooms", [])
        currency = proj.get("currency", "")
        total = sum(r.get("total_cost", 0) for r in rooms)
        room_lines = "\n".join(
            f"  {r.get('name')}: {r.get('area_m2', 0):.1f} m² "
            f"@ {r.get('rate_per_m2', 0):,.0f} {currency}/m² "
            f"= {r.get('total_cost', 0):,.0f} {currency}"
            for r in rooms
        )
        return (
            f"Project: {proj.get('name')} | Currency: {currency} | "
            f"Total: {total:,.0f} {currency}\nRooms:\n{room_lines}"
        )
