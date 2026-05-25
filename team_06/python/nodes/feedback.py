from typing import Any
import json

def build_feedback_node(llm: Any) -> Any:
    """Display layout summary with daylight breakdown and ask user feedback."""
    
    def feedback(state: dict) -> dict:
        layout_json = state.get("layout_json_string", "{}")
        eval_results = state.get("evaluation_json_string", "{}")
        iteration = state.get("iteration", 0)
        
        # Parse layout
        try:
            if isinstance(layout_json, str):
                layout = json.loads(layout_json)
            else:
                layout = layout_json
            if not isinstance(layout, dict):
                layout = {}
        except:
            layout = {}

        # Extract room summary
        rooms = layout.get('rooms', [])
        room_programs = {}
        for room in rooms:
            prog = room.get('attributes', {}).get('program', 'unknown')
            room_programs[prog] = room_programs.get(prog, 0) + 1
        
        area = layout.get('apartment', {}).get('attributes', {}).get('area', 'N/A')
        
        # Parse evaluation - categorize by daylight
        eval_data = {}
        best_daylight = []    # > 3.0
        good_daylight = []    # 1.0-3.0
        poor_daylight = []    # 0.0-0.99
        
        try:
            if isinstance(eval_results, str):
                eval_data = json.loads(eval_results)
            else:
                eval_data = eval_results
            
            if isinstance(eval_data, dict):
                for room_id, room_eval in eval_data.items():
                    if isinstance(room_eval, dict):
                        dl = room_eval.get('daylight')
                        name = room_eval.get('name', room_id)
                        prog = room_eval.get('program', '?')
                        
                        if dl is not None and isinstance(dl, (int, float)):
                            entry = f"{name} ({dl})"
                            if dl > 3.0:
                                best_daylight.append(entry)
                            elif dl > 1.0:
                                good_daylight.append(entry)
                            elif dl > 0.0:
                                poor_daylight.append(entry)
        except:
            pass
        
        # Format room list
        room_list = ", ".join([f"{count} {prog}" for prog, count in room_programs.items()]) or "no rooms"
        
        # Build daylight description
        daylight_desc = ""
        if best_daylight:
            daylight_desc += f"✨ Excellent: {', '.join(best_daylight)}\n"
        if good_daylight:
            daylight_desc += f"☀️ Good: {', '.join(good_daylight)}\n"
        if poor_daylight:
            daylight_desc += f"🌑 Limited: {', '.join(poor_daylight)}\n"
        if not daylight_desc:
            daylight_desc = "No daylight data"
        
        feedback_message = f"""✨ **Layout Summary:**
{room_list} | Area: {area} m²

📊 **Daylight:**
{daylight_desc}
**Feedback?**
- "end" → finalize
- "no" or "different" → search again  
- "change rooms" → new programs
- "change boundary" → adjust outline"""

        return {
            "final_response": feedback_message,
            "iteration": iteration + 1,
        }
    
    return feedback