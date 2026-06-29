# LLM Nodes

Three nodes call the LLM. The others are deterministic.

---

## reason

**Role** — parse the user's free-text into a structured search payload and decide what to do next.

**Input from state**
- `user_prompt` — latest user message
- `topology_graph_json_string` — existing payload from previous turns (graph + household + description)
- `feedback_history` — all prior user turns

**System prompt** — instructs the model to act as an architect assistant that reads the current summary and returns a single updated JSON object. Defines room category rules (no kitchen, study→bed, wc vs bath, etc.), what goes in graph vs household vs description, and when to set `latest_prompt_useful`.

**LLM call**
```
system: SYSTEM_PROMPT
user:   current graph / household / description + feedback_history + user_prompt
```

**Output schema (LLM)**
```json
{
  "latest_prompt_useful": true,
  "graph": {
    "programs": ["bed", "bed", "bath"],
    "access_pairs": [["bed", "bath"]],
    "adjacency_pairs": [],
    "not_adjacency_pairs": [],
    "centrality": [["living", "central"]],
    "room_sizes": [["bed", "large"]],
    "windows": [["bed", 2]],
    "shape": "rectangular",
    "total_area": 75,
    "aspect_ratio": null,
    "compactness": null
  },
  "household": [{ "name": "", "relationship": "", "info": "" }],
  "description": "compact two-bedroom for a couple, bright living area"
}
```

**State output**
- `topology_graph_json_string` — serialised updated payload
- `reason_result` — `"search"` | `"evaluate"` | `"feedback"`
- `clarification` — question to surface if going to feedback

---

## evaluate

**Role** — score the selected layout against the brief and write a short qualitative comment.

**Input from state**
- `layout_json_string` — current layout geometry + room attributes
- `topology_graph_json_string` — structured brief (graph + description)
- `layout_id` — used for lifestyle embedding lookup

**Deterministic subscores** (no LLM)
| id | weight | what it measures |
|----|--------|-----------------|
| room_fit | 30 % | required programs present |
| lifestyle_fit | 25 % | cosine similarity of description embedding to layout embedding |
| access_fit | 20 % | required door connections |
| adjacency_fit | 12 % | required/forbidden adjacencies |
| size | 13 % | preferred room sizes |

`fit_score` = weighted average of available subscores (0–100).

**LLM call** — generates exactly 2 plain-text sentences summarising fit.
```
system: write 2 sentences, no scores, no markdown
user:   user brief + planfinder description + actual room counts
```

**Output schema (`evaluation_json_string`)**
```json
{
  "fit_score": 74,
  "subscores": [
    { "id": "room_fit", "label": "Rooms", "score": 80, "available": true, "details": null },
    ...
  ],
  "chat_summary": "The layout matches your bedroom count...",
  "daylight_score": 65,
  "daylight_rooms": [{ "room": "bed", "score": 80 }, ...]
}
```

**State output**
- `evaluation_json_string` — serialised summary above
- `clarification` — `chat_summary` + fixed closing sentence (shown in UI)

---

## routine

**Role** — generate an hourly daily schedule for every household member and pet.

**Input from state**
- `layout_json_string` — room list (ids + programs + areas)
- `topology_graph_json_string` — household list (names, relationships, lifestyle info)
- `feedback_history` + `user_prompt` — full conversation brief

**System prompt** — strict format rules: 17 steps per persona (06:00–22:00), `null` = away, `["<room_id>", "<activity>"]` = at home. Defines default adult schedule, exceptions (WFH, child, retired, baby), conflict rules (no two people in same bathroom at same time), pet behaviour, and outdoor → null rules.

**LLM call**
```
system: SYSTEM_PROMPT
user:   full conversation brief + available room list + time slots
```

**Output schema (LLM → normalised)**
```json
{
  "time_slots": ["06:00", "07:00", ...],
  "personas": [
    {
      "persona": "Anna",
      "color": "#4A7CA8",
      "kind": "person",
      "steps": [
        { "room": "room_3", "label": "sleeping" },
        null,
        ...
      ]
    }
  ]
}
```
`step` is `null` when away, or `{ room, label }` when home. Invalid room IDs and forbidden programs (circulation, storage) are stripped to `null` in post-processing.

**State output**
- `routine_json_string` — serialised payload above
- `routine_warning` — non-fatal message shown in UI if fallback was used
