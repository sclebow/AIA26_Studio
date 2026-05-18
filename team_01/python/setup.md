# Grasshopper MCP Agent — Startup Checklist

Follow these steps **every time** before running the agent.

---

## Step 1 — Activate the Virtual Environment

Open **Windows PowerShell** (`Win + R` → type `powershell` → Enter).

Navigate to the repo root:
```powershell
cd D:\IAAC\AIA26\Studio_AIA\Database\AIA26_Studio # its your destination address
```

Activate the venv:
```powershell
.\.venv\Scripts\Activate.ps1
```

✅ You should see `(.venv)` at the start of your terminal line.

---

## Step 2 — Open LM Studio

Open the **LM Studio** application from your desktop or Start menu.

---

## Step 3 — Load the Model

1. In LM Studio, click the **Chat** tab (top of left sidebar)
2. At the top of the window, click the model selector dropdown
3. Find and load: **`meta-llama-3.1-8b-instruct`**
4. Wait until the model finishes loading (progress bar completes)

✅ You should see the model name shown as active at the top.

---

## Step 4 — Start the LM Studio Server

1. In LM Studio, click **"Local Server"** or **"Developer"** in the left sidebar
2. Click **"Start Server"**
3. Wait for the status message — it should say something like:

```
Reachable at 127.0.0.1:1234
```

4. **Note down the address shown** (it should always be `127.0.0.1:1234`)

✅ Confirm it works — open your browser and go to:
```
http://localhost:1234/v1/models
```
You should see a JSON response with the model name.

---

## Step 5 — Open Grasshopper and Check the Port

1. Open **Rhino**, then open your team's Grasshopper file:
   ```
   team_01\gh\team_01_working.gh
   ```
2. Look at the **panel** connected to the free-port script — it will show a number like `3001`, `3002`, etc.
3. **Note that port number**

### Update `mcp.json` with the correct port

Open `mcp.json` (at the repo root) in **VS Code** and update the port to match what Grasshopper shows:

```json
{
  "mcpServers": {
    "Swiftlet": {
      "command": "C:\\Users\\Scott\\AppData\\Roaming\\McNeel\\Rhinoceros\\packages\\8.0\\swiftlet\\0.2.0\\SwiftletBridge.exe",
      "args": [
        "http://localhost:3001/mcp/"
      ]
    }
  }
}
```

Replace `3001` with whatever port Grasshopper panel shows today.

> **Also update in LM Studio:** Go to Local Server → MCP settings → update the Swiftlet URL to the same port.

---

## Step 6 — Run the Agent

In **VS Code**, open the terminal (`Ctrl + `` ` ```) and make sure you are in the right folder:

```powershell
cd D:\IAAC\AIA26\Studio_AIA\Database\AIA26_Studio\team_01\python
```

Run the agent with your prompt:

```powershell
python main.py "your instruction here"
```

### Example prompts:
```powershell
python main.py "delete the kitchen"
python main.py "add a window to Bedroom 1"
```

✅ You should see:
```
Discovered MCP tools: [...]
Reasoning with LLM...
Agent response:
...
```

---

## Quick Reference

| Service | Address | Config file |
|---|---|---|
| LM Studio API | `http://localhost:1234/v1/` | `.env` |
| Swiftlet MCP | `http://localhost:300X/mcp/` | `mcp.json` |

## `.env` should look like this:
```dotenv
LLM_PROVIDER = "local"
LOCAL_LLM_ENDPOINT = "http://localhost:1234/v1/"
```

---

> If anything fails, check: (1) venv is activated, (2) LM Studio server is running, (3) Grasshopper is open with the correct port, (4) `mcp.json` port matches Grasshopper panel.