Foreman Agent
================

# Description
The Foreman Agent is an LLM-based agent designed to run all six of the AIA26 Studio Agents, each with its own unique expertise. The Foreman Agent routes the user's query to the appropriate group of agents, and orchestrates the responses to provide a comprehensive answer.  Each of the six agents has their own agent.md file with more details on their specific capabilities and expertise.

# Example Prompts
1. "Help me layout an apartment and determine the structural elements in the layout."
   - The Foreman Agent will route this query to the InHabit Agent, who will determine the apartment layout, then route the layout and query to the Studi Agent, who will add the structural elements and provide structural analysis.
2. "I recently broke my knee so I am expanding the area of my apartment kitchen but I am worried it will be too expensive to remodel. Can you help me figure out how to remodel my kitchen on a budget?"
   - The Foreman Agent will route this query to the Spatial Flow Agent to determine the navigation flow of the existing kitchen, then route the flow and query to the InHabit Agent, who will provide a layout for the expanded kitchen, then route the layout and query to the Struct Agent, who will determine the structural elements of the remodel, then route the structural elements and query to the Cost Agent, who will provide a cost estimate for the remodel.
3. "The sunlight in my apartment is too bright in the afternoon and it's making it hard for me to work.  Can you help me figure out how to design a new layout for my apartment that will reduce the amount of sunlight in the afternoon?"
   - The Foreman Agent will route this query to the Sensorial Agent, who will analyze the sunlight patterns in the existing apartment, then route the sunlight analysis and query to the InHabit Agent, who will provide a new layout for the apartment that reduces the amount of sunlight in the afternoon, then route the new layout and query back to the Sensorial Agent, who will analyze the sunlight patterns in the new layout to ensure it meets the user's needs.
4. "I recently purchased a plot of land to build a six apartment building on, help me figure out some potential layouts for the building and determine the structural elements of the building."
   - The Foreman Agent will route this query to the Site Agent to analyze the plot of land and provide potential layouts for the exterior walls of the building, then route the layouts and query to the InHabit Agent, who will provide potential layouts for the interior walls of the building, then route the layouts and query to the Struct Agent, who will determine the structural elements of the building based on the layouts provided by the Site and InHabit Agents.