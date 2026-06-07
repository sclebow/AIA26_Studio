# Team 06 CLI

This document describes how to run the Team 06 Python agent from the command line.

## Entry Point

Run the agent from:

```powershell
cd team_06/python
python main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom"
```

If you are using the workspace virtual environment:

```powershell
cd team_06/python
..\..\.venv\Scripts\python.exe main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom"
```

## Arguments

- `--prompt` Required. The user instruction sent into the graph.
- `--layout_json` Optional. A JSON object string used to override the bootstrapped layout context for this run.
- `--hide_layout_json` Optional. Suppresses the `Edited Layout JSON:` block in console output. Useful for UI/chat views.

## Behavior

The CLI bootstraps the Team 06 runtime, runs the graph, and prints progress updates as `Status:` lines.

If the graph determines that more user input is needed, it returns an explicit `needs_user_input` signal. When the process is attached to an interactive terminal, the CLI prompts for another turn with:

```text
You:
```

This allows back-and-forth clarification in direct CLI use.

## Output Format

### Default output

By default, the CLI prints:

```text
Status: Initializing agent runtime.
Status: Analyzing your request.
...
Final Response:
<agent response>
Edited Layout JSON:
<layout json or No layout changes>
```

This is the recommended mode for orchestrators that need the edited layout payload in the terminal output.

### UI-friendly output

To keep progress updates and final text but omit the layout JSON block:

```powershell
python main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom" --hide_layout_json
```

This prints:

```text
Status: Initializing agent runtime.
Status: Analyzing your request.
...
Final Response:
<agent response>
```

## Using `--layout_json`

`--layout_json` must be a valid JSON object string.

Example:

```powershell
python main.py --prompt "Adapt this layout for better daylight" --layout_json '{"outline": [[0,0], [6,0], [6,4], [0,4]], "rooms": []}'
```

If parsing fails, the CLI exits with code `1` and prints an error message.

Example error:

```text
Error: Invalid --layout_json: Expecting property name enclosed in double quotes
```

## Recommended Usage Patterns

### Orchestrator mode

Use when another agent or service needs the returned layout JSON in the terminal output.

```powershell
python main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom"
```

### UI mode

Use when a frontend or chatbox should show progress and final text without dumping the full layout JSON to the screen.

```powershell
python main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom" --hide_layout_json
```

### Layout override mode

Use when an external orchestrator already has a layout and wants Team 06 to work from that layout instead of only the bootstrapped file-based input.

```powershell
python main.py --prompt "Improve this layout" --layout_json '{"outline": [[0,0], [8,0], [8,6], [0,6]], "rooms": []}'
```

## Notes

- The CLI still loads the runtime and tool connections through `bootstrap()`.
- When `--layout_json` is provided, it replaces `ctx.layout_data` before the graph runs.
- The graph emits curated `Status:` lines for user-facing progress.
- The clarification loop is controlled by the graph's explicit `needs_user_input` field, not by text matching in `main.py`.