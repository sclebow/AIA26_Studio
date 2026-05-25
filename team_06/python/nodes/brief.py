from typing import Any
import json
from tools.graph_searcher import build_topology_graph
import networkx as nx
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an architect assistant designing residential floor plans.

AVAILABLE ROOMS: bedroom, bathroom, kitchen, living, foyer, extra

TASK: Extract household info from user input, then infer room programs.

INFERENCE RULES:
- People count → bedrooms: 1 person = 1 bed; 2 adults = 1-2 beds; family of 4+ = 2-3 beds
- "kids" or "children" → add +1 bedroom if family
- "work from home" or "office" → add "extra" (workspace)
- "nurse on nights" or "daytime sleep" → note adjacency
- "pets" → may need extra space
- "entertaining" or "guests" → living room adjacency matters

EXTRACTION:
Always include: bathroom
- Add foyer if user mentions "entry", "entrance", "hallway"
- Add extra if workspace, storage, or guest needs
- Set connection_preference:
  * "connected" if adjacency matters (work from home, frequent hosting, daytime sleep)
  * "any" otherwise

SUFFICIENCY:
- "2 bedrooms" alone IS sufficient input → extract as ["bedroom", "bedroom", "kitchen", "living", "bathroom"]
- "apartment with 3 bedrooms" IS sufficient
- "I want a home" ALONE is too vague → requires_clarification: true
- "just apartment" or "any layout" → requires_clarification: true

INPUT: User description OR explicit room list ("2 bedrooms and kitchen")
OUTPUT JSON: {"programs": [...], "connection_preference": "any"|"connected", "requires_clarification": false}

Only set requires_clarification: true if user gave NO room count or NO specific details at all."""

def build_brief_node(llm: Any) -> Any:
    """Parse user input → extract programs or ask for clarification."""
    
    def brief(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "")
        iteration = state.get("iteration", 0)
        
        # First attempt: extract programs
        extract_prompt = f"""User input: {user_prompt}

Extract household info and infer room programs.
Return JSON: {{"programs": ["bedroom", "kitchen", "living", "bathroom", ...], "connection_preference": "any"|"connected", "requires_clarification": false}}

If input too vague (e.g., just "apartment"), set requires_clarification: true and add clarification_needed: "please describe your household"."""
        
        try:
            response = llm.invoke(_SYSTEM_PROMPT + "\n\n" + extract_prompt)
            
            # Log tokens if available
            if hasattr(response, 'response_metadata'):
                usage = response.response_metadata.get('usage', {})
                inp = usage.get('input_tokens', 0)
                out = usage.get('output_tokens', 0)
                logger.info(f"📊 brief tokens: {inp} in + {out} out = {inp + out} total")
                
            result = json.loads(response.content.strip())
            
            programs = result.get("programs", [])
            connection = result.get("connection_preference", "any")
            needs_clarification = result.get("requires_clarification", False)
            
            if not needs_clarification and programs:
                topology = build_topology_graph(programs, connection)
                topology_json = json.dumps(nx.node_link_data(topology))
                
                return {
                    "topology_graph_json_string": topology_json,  
                    "iteration": iteration + 1,
                }
            elif needs_clarification:
                # Ask for clarification - DON'T set final_response, let main.py handle it
                return {
                    "final_response": result.get("clarification_needed", 
                                                "Tell me more: how many people, any kids/pets, work from home?"),
                    "iteration": iteration + 1,
                }
        except Exception as e:
            pass
        
        # Fallback: couldn't parse → ask for help
        if iteration == 0:
            return {
                "final_response": "I need more details. How many people live with you? Any kids or pets? Do you work from home?",
                "iteration": iteration + 1,
            }
        else:
            # User gave second response, try again
            extract_prompt = f"""Previous context: {user_prompt}

Now retry extraction. Return JSON: {{"programs": [...], "connection_preference": "any"}}"""
            
            try:
                response = llm.invoke(_SYSTEM_PROMPT + "\n\n" + extract_prompt)
                result = json.loads(response.content.strip())
                programs = result.get("programs", ["bedroom", "kitchen", "living", "bathroom"])
                
                topology = build_topology_graph(programs, result.get("connection_preference", "any"))
                topology_json = json.dumps(nx.node_link_data(topology))
                
                return {
                    "topology_graph_json_string": topology_json,
                    "iteration": iteration + 1,
                }
            except:
                # Final fallback - use defaults
                topology = build_topology_graph(["bedroom", "kitchen", "living", "bathroom"], "any")
                topology_json = json.dumps(nx.node_link_data(topology))
                return {
                    "topology_graph_json_string": topology_json,
                    "iteration": iteration + 1,
                }
    
    return brief