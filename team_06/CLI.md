# Team 06 CLI

This document describes how to run the Team 06 Python agent from the command line.

## Entry Point

### Start both frontend and backend

From the Team 06 folder, you can now launch both services with one command:

```powershell
cd team_06
.\start_local.ps1
```

If PowerShell execution policy gets in the way, use:

```powershell
cd team_06
.\start_local.cmd
```

This opens two PowerShell windows:

- one for the backend on `http://127.0.0.1:8000`
- one for the frontend via `npm run dev`

Run the backend for the frontend from:

```powershell
cd team_06/python
python main.py
```

If you are using the workspace virtual environment:

```powershell
cd team_06/python
..\..\.venv\Scripts\python.exe main.py
```

This starts the FastAPI backend on `http://127.0.0.1:8000`, which is what the Vue frontend expects by default.

If you want the old terminal-only chat flow, pass a prompt explicitly:

```powershell
cd team_06/python
python main.py --prompt "I want an apartment with a living and a bedroom connected to bathroom"
```

## Arguments

- `--prompt` Optional. When provided, runs a direct CLI chat session instead of starting the backend server.
- `--layout_json` Optional. A JSON object string used to override the bootstrapped layout context for this run.
- `--hide_layout_json` Optional. Suppresses the `Edited Layout JSON:` block in console output. Useful for UI/chat views.
- `--serve` Optional. Explicitly starts the FastAPI backend server.
- `--host` Optional. Backend server host. Default: `127.0.0.1`.
- `--port` Optional. Backend server port. Default: `8000`.
- `--reload` Optional. Enables auto-reload in backend server mode.

## Behavior

With no `--prompt`, `main.py` starts the Team 06 FastAPI backend server for the frontend.

With `--prompt`, the CLI bootstraps the Team 06 runtime, runs the graph, and prints progress updates as `Status:` lines.

If the graph determines that more user input is needed, it returns an explicit `needs_user_input` signal. When the process is attached to an interactive terminal, the CLI prompts for another turn with:

```text
You:
```

This allows back-and-forth clarification in direct CLI use.

## Output Format

### Default backend mode

```powershell
python main.py
```

This serves the API for the frontend chat UI. You then start the frontend separately with `npm run dev` in `team_06/frontend`.

### CLI output

When `--prompt` is provided, the CLI prints:

```text
Status: Initializing agent runtime.
Status: Analyzing your request.
...
Final Response:
<agent response>
Edited Layout JSON:
<layout json or No layout changes>
```

This is the recommended mode for terminal orchestration that needs the edited layout payload in the output.

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

### Backend-for-frontend mode

Use when the Vue frontend should open first and the user will type directly into the chat box.

```powershell
python main.py
```

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