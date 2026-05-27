Sensi Agent
===========

# Description
Sensi is an LLM-based agent that analyzes architectural layouts for sensorial comfort across six senses — visual, acoustic, thermal, olfactory, tactile, and proprioceptive. Sensi first builds a user persona through guided onboarding, then evaluates any spatial layout against that persona: scoring comfort per room, detecting sensorial conflicts, and proposing feasible modifications ranked by priority and cross-sense consequence.

# Example Prompts
1. "Analyze the comfort of my apartment layout."
   - Sensi loads the layout, computes comfort scores across 6 senses for all rooms against the user's persona, detects sensorial conflicts, and generates ranked improvement suggestions.

2. "My bedroom feels acoustically uncomfortable — what can I change?"
   - Sensi identifies the acoustic conflict, reasons through its root cause, and generates targeted suggestions. If the user asks to test a specific material change, Sensi modifies the layout and re-scores to show the before/after comfort delta.

3. "Can you compare how this layout performs for me vs. my partner?"
   - Sensi routes to the persona comparison tool, scoring the same layout against two different persona profiles and surfacing which spaces serve each person poorly and why.

4. "Does my apartment have enough biophilic connection?"
   - Sensi audits greenery presence across all rooms, and if lacking, generates plant/furniture placement suggestions before re-scoring to show the biophilic improvement.

5. "I already got the analysis — what exactly causes the living room thermal conflict?"
   - Sensi detects the follow-up intent and routes to detail_respond, synthesizing cached conflict reasoning and score interpretation from the active session without re-running any analysis tools.
