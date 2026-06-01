from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm

# ---------------------------------------------------------------------------
# System prompt — edit this to change how the agent thinks and behaves.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the reasoning module of an agent with the following description: 
{agent_description}

You have access to the following agents to help you complete your task:
{agent_catalog}

You may response with one of three actions:
- "final": the agent has completed the task and has a final response. No more interaction is needed.
- "agent": the agent needs to use one of the other agents to complete the task, and will specify which one and with what arguments.
- "further_thought": the agent needs to think more and will specify more information for itself to consider in the next reasoning step.

Return strictly valid JSON with exactly this shape:
{{
  "action": "final" | "agent" | "further_thought",
  "response": "thoughts or final answer for the user, depending on the action",
  "agent_calls": [{{"name": "<agent-name>", "arguments": {{...}}}}, ...]
}}

Output rules:
- Return JSON only, with no prose or explanation.
- Do not use markdown code fences.
- If action is "final", set agent_calls to [] and put the answer in response.
- If action is "agent", set response to "" and put one or more agent calls in agent_calls.
- If action is "further_thought", set response to your current thoughts for yourself, set agent_calls to [].
"""


# ---------------------------------------------------------------------------
# Reason node — the LLM decision step in the graph.
# ---------------------------------------------------------------------------

def add_agent_descriptions_to_state(state):
    """Helper function to format the agent catalog for the system prompt.
    The foreman description is in ./foreman/agent.md
    The tool descriptions are in ./team_01/agent.md, ./team_02/agent.md, etc.
    This function reads those files and adds them to the state as a formatted string for the system prompt.
    """

    # Read the foreman description
    with open("foreman/agent.md", "r") as f:
        foreman_description = f.read()
        # print(f"Foreman description:\n{foreman_description}\n")
        # state["agent_description"] = foreman_description
        state["agent_description"] = "You can answer any question about the world."

    # Read the agent descriptions
    agent_descriptions = []
    num_agents = 6
    for i in range(1, num_agents + 1):
        try:
            with open(f"team_{i:02d}/agent.md", "r") as f:
                agent_description = f.read()
                # print(f"Agent {i} description:\n{agent_description}\n")
                agent_descriptions.append(agent_description)
        except FileNotFoundError:
            print(f"Warning: agent.md not found for team_{i:02d}, skipping.")

    state["agent_catalog"] = "\n".join(agent_descriptions)

def build_reason_node(llm):
    """Return a reason node function ready to be added to a LangGraph StateGraph."""

    def reason_node(state):
        print("\nReasoning with LLM...")
        state["iteration"] = int(state.get("iteration", 0)) + 1

        # Format the system prompt
        add_agent_descriptions_to_state(state)

        result = call_llm(llm, SYSTEM_PROMPT, state["messages"])

        # If the LLM decided no more actions are needed (action is final), set the final response in the state and clear pending tool calls
        if result["action"] == "final":
            state["final_response"] = result["response"]
            state["pending_tool_calls"] = None

        # If the LLM decided the action is to use a tool, set the pending tool calls
        elif result["action"] == "agent":
            state["pending_tool_calls"] = result["agent_calls"]

        else:  # further thought
            # Feed the thought back into the conversation so the next step can build on it.
            thought = result["response"]
            state["messages"].append({"role": "assistant", "content": thought})
            state["pending_tool_calls"] = None
            print(f"LLM thought: {thought}")

        if state["iteration"] >= state["max_iterations"] and state.get("final_response") is None:
            state["final_response"] = "I could not produce a final response within the iteration limit."

        return state

    return reason_node
