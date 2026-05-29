# Permanence_OS

# Description
The Permanence_OS is an LLM-based structural design agent for the AIA26 Studio pipeline. It specializes in structural grid generation, element analysis, and material selection. Cross-agent orchestration — routing queries to the other five specialist agents and synthesizing responses across agents — is planned for the future pipeline. Each agent has its own agent.md with details on its specific capabilities.

# Example Prompts
1. "Add a structural grid to my apartment layout and evaluate whether it can support the loads."
   - The Permanence_OS generates a column grid from the layout outline, runs first-principles beam and column checks (bending, shear, deflection, buckling), prompts the architect for material selection and use-type loads (SDL + LL), and returns a full evaluation table with pass/fail results per element.
2. "I want to open up my living room by removing column C_2 — is that structurally feasible?"
   - The Permanence_OS simulates the column removal, traces the beam chain to the nearest remaining support, re-evaluates the extended span, and presents the architect with options: upgrade the beam section, add a midspan column, or switch to a stronger material. If the architect confirms, the column is removed from the JSON and connected beams are merged into a single longer beam.
3. "What are the section sizes for the CD grid line beams, and which beam has the longest span?"
   - The Permanence_OS reads the per-element layout context directly and answers without running any structural calculations or prompting for material or loads.
4. "I want to build a six-apartment building on a narrow plot — what structural system would work and what will it cost?"
   - *(Future pipeline)* The Permanence_OS routes to the Site Agent to analyze the plot constraints, then generates a structural grid and evaluates material options (RCC, Steel, Timber) for the given spans, then routes the structural output to the Regulation & Cost Agent for a cost estimate.
5. "Beam CD_1 is failing — add a midspan column under it and re-evaluate."
   - The Permanence_OS identifies the failing beam, adds a midspan column at the exact midpoint, splits CD_1 into two half-span beams, re-evaluates all elements, and shows a before/after comparison. If the shorter spans now pass, the new column and split beams are written to the layout JSON.
6. "Find the minimum sufficient sections for steel."
   - The Permanence_OS auto-detects steel from the prompt, skips the material picker, and asks only for SDL and live load. It then applies XS steel sections across all elements and upgrades each failing element step by step — returning the smallest possible IPE profiles that pass all checks for the given loads. SDL and live load choices are saved to disk and pre-filled on the next run.
