InHabit Agent
================

# Description
The InHabit Agent is an LLM-powered assistant specialized in generating, adapting, and evaluating apartment layouts. It focuses on spatial adjacency, required programs, daily routines, daylight, and room size standards. The agent can interactively collect household requirements, propose or adapt layouts, and provide feedback based on both user preferences and architectural rules. It supports both conversational and direct command prompts for flexible design workflows.

# Example Prompts
1. "Chat."
   - The InHabit Agent enters chat mode, asking a series of questions about the household (number of people, ages, activities, preferences) to build a user profile. It then adapts a layout to the input outline, runs daylight analysis, evaluates the result, and requests user feedback.
2. "I would like an apartment with 2 bedrooms and a kitchen connected to living"
   - The agent interprets the requirements, selects or generates a suitable layout, adapts it to the input boundary, and evaluates it for daylight, room size, and spatial proportions.
3. "Select layout-4 and adapt it to the input outline"
   - The agent selects the specified layout from the dataset, adapts it to the given boundary, and proceeds with the full evaluation and feedback pipeline.
4. "Evaluate the current layout and summarise issues."
   - The agent analyzes the current layout for daylight, checks compliance with room size and dimension rules, and summarizes any issues or mismatches with user preferences.

# Example chat mode interaction

1. "How many people will live in the apartment? Please provide names, ages, and relationships."
User: "Me (36), my partner (32), and our child (2)."
2. "Do you have any pets? If so, what type and size?"
User: "We have a big dog."
3. "What are the main activities at home (e.g., work, cook, hobbies)? When do they happen and who participates?"
User: "We both work from home, and our child plays in the living room."
4. "Do you have preferences for rooms (type, size, connections, usage times, or who uses them)?"
User: "We want the kitchen connected to the living room, and a quiet workspace."