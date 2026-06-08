InHabit Agent
================

# Description
The InHabit Agent is an LLM-powered assistant specialized in generating, adapting, and evaluating apartment layouts. It focuses on spatial adjacency, required programs, daily routines, daylight, and room size standards. The agent can interactively collect household requirements, propose or adapt layouts, and provide feedback based on both user preferences and architectural rules. It supports both conversational and direct command prompts for flexible design workflows.

# Example Prompts
1. "I would like an apartment with bedroom connected to bathroom, the living next to entry door, and a kitchen island."
   - The agent interprets the requirements, search for the best match in the dataset, adapts it to the input boundary (if provided), run daylight analysis and evaluate the results against the requirements.
2. "I want to check how well layout-xxx fits my requirements."
   - The agent selects the specified layout from the dataset, adapts it to the given boundary (if provided), and proceeds with the full evaluation and feedback pipeline.
3. "The household is now a parent and child, with two bedrooms and adjacency between kitchen and living. Score the current layout."
   - The agent evaluate the current layout against the new brief.