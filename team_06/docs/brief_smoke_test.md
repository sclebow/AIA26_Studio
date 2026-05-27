# Team 06 Brief Smoke Test

## Example 1

**Input**

"find me 2-bedroom layouts"

**Expected mode**

PIPELINE

**Expected action value**

`tool`

**Expected tool call or final_response shape**

Call `layout_graph_search` with `programs=["bedroom", "bedroom", "kitchen", "living"]` and `connection_type="any"`.
Should match `layout-4`.

**Interaction rules that should fire**

No BRIEF-specific interaction rule is the focus here; this is a direct PIPELINE retrieval turn.

## Example 2

**Input**

"I live with my partner Sara, she's a nurse on night shifts, I'm a freelance illustrator who works from home, we have a big dog, we cook together a lot"

**Expected mode**

BRIEF

**Expected action value**

`final`

**Expected tool call or final_response shape**

The agent extracts 2 adults and 1 dog, identifies that the user works from home with calls and that Sara sleeps during the day, then asks ONE focused follow-up to confirm the household before proceeding.

**Interaction rules that should fire**

- `Ask at most one focused question per turn.`
- `Prefer inference + brief confirmation over open-ended questions.`

## Example 3

**Input**

"Yes, that's right"

**Expected mode**

BRIEF

**Expected action value**

`final`

**Expected tool call or final_response shape**

The agent advances to Step 3 and says approximately: "Two things to flag with our current 6-layout dataset: (a) there's no dedicated studio or office program — your illustration workspace will share the bedroom or living. (b) for Sara's daytime sleep, the bedroom and kitchen should be separated — I'll prioritize that in the search. OK to proceed?"

**Interaction rules that should fire**

- `When the user mentions something that maps to unsupported_concepts, do not silently drop it — surface the limitation, propose a workaround, and add to acknowledged_limitations[] if the user accepts.`

## Example 4

**Input**

"Sounds good, find me a layout"

**Expected mode**

BRIEF

**Expected action value**

`final`

**Expected tool call or final_response shape**

The agent runs Step 4, confirms the brief in 2–3 sentences, and emits `BRIEF_READY:` followed by the full brief payload as `final_response`.
The payload includes `derived_programs` such as `["bedroom", "kitchen", "living", "bathroom"]`, a `connection_preference`, `acknowledged_limitations` listing the workspace and adjacency points, and `brief_complete: true`.
Note: the user's `find me a layout` is a pipeline verb appearing mid-brief, but Step 4 is still the right behavior because the brief is essentially complete. The user's next message triggers PIPELINE mode for retrieval.

**Interaction rules that should fire**

- `When emitting BRIEF_READY:, use action: 'final' with the full brief payload in final_response. Do NOT call layout_graph_search in the same turn.`

## Example 5

**Input**

"OK find me a layout"

**Expected mode**

PIPELINE

**Expected action value**

`tool`

**Expected tool call or final_response shape**

The agent reads the brief from the prior assistant message by looking for `BRIEF_READY:`, extracts `derived_programs` and `connection_preference`, then calls `layout_graph_search(programs=<derived_programs>, connection_type=<connection_preference>)`.
It loads the best match, likely `layout-1` or `layout-3`.

**Interaction rules that should fire**

- `When the user's next message after BRIEF_READY: indicates they want a layout (any pipeline verb), the agent enters PIPELINE mode and calls layout_graph_search using derived_programs as programs and connection_preference as connection_type. Read these from the brief in message history.`
