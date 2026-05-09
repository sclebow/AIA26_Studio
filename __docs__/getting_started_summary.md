# AIA26 Studio Project Summary

## Overview

This is a **multi-team studio project** where 6 teams build **MCP (Model Context Protocol) tools in Grasshopper** and **Python agents** that can call those tools. The goal is creating a shared repository of computational design tools accessible to AI agents.

## Key Concepts

**Architecture:**
- **Grasshopper** → builds MCP tools (geometry/design operations)
- **Swiftlet MCP Server** → exposes Grasshopper tools via HTTP
- **Python Agent** (LangGraph) → reasons and calls tools via MCP
- **LLM** → drives the agent's decision-making

`
LLM Client → Swiftlet MCP Server → Grasshopper Tools → Results
`

## Repository Structure

- **`team_01/` through `team_06/`** — one folder per team
  - **`gh/`** — Grasshopper clusters and test file
  - **`python/`** — Python agent code (LangGraph + MCP)
- **`team_base/`** — older reference (ignore for now)
- **`mcp.example.json`** — template for MCP configuration

## Critical Rules

| Rule | Details |
|------|---------|
| **One branch per team** | Work only in your team's branch |
| **Edit only your folder** | `team_XX/` only—no touching other teams |
| **Weekly PR deadline** | Sunday 11:59 PM Barcelona time into `main` |
| **Coordinate tools** | Avoid duplicating other teams' work |

---

# Getting Started - End-to-End Workflow

## Step 1: Initial Setup

### 1.1 Clone and Branch
```bash
# Clone the repository
git clone <repository-url>
cd AIA26_Studio

# Switch to your team's branch (example for team 1)
git checkout team_01
```

### 1.2 Install Prerequisites
- **Rhino + Grasshopper** with **Swiftlet** plugin installed
- **Python 3.10+** on your PATH
- **Git** or GitHub Desktop

### 1.3 Configure MCP
```bash
# At repository root
cp mcp.example.json mcp.json
# Edit mcp.json with your Swiftlet port (see step 2.3)
```

## Step 2: Grasshopper Tools Setup

### 2.1 Open Your Team's Working File
- Navigate to `team_XX/gh/team_XX_working.gh`
- Open in Grasshopper

### 2.2 Understand the Clusters
Two critical clusters:
- **`team_XX_definition_cluster.ghcluster`** — defines tool parameters and metadata
- **`team_XX_result_cluster.ghcluster`** — routes tool calls to logic

### 2.3 Start Swiftlet Server
1. The working file includes a **C# script** that finds a free port (3001-3100)
2. Check the panel output for the **actual port** (e.g., 3005)
3. Right-click **MCP Server component** → **"Copy MCP Config"**
4. Update `mcp.json` with this config (merge, don't overwrite)

### 2.4 Build Your Tools
**In the definition cluster:**
- Define tool **Name** (no spaces), **Description**, **Parameters**
- Each parameter needs: Name, Type, Description, Required flag

**In the result cluster:**
- Route tool calls to logic branches
- **Tool names must match** definition cluster
- **Order must match** routing logic
- Connect **OK output** to **Gate Or** input

## Step 3: Test Tools (LM Studio or Claude Desktop)

### 3.1 Configure Client
- Edit `mcp.json` to point to `http://localhost:<port>` (from step 2.3)
- For LM Studio or Claude Desktop, paste the MCP config

### 3.2 Test Tool Calls
- Start a chat in LM Studio/Claude Desktop
- Ask the LLM to call your tools
- Verify results in Grasshopper Data Recorder

## Step 4: Python Agent Setup

### 4.1 Create Virtual Environment
```bash
cd team_XX/python
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

### 4.2 Install Dependencies
```bash
pip install -r requirements.txt
```

### 4.3 Configure Environment
```bash
# Copy example env file
cp .env.example .env

# Edit .env with:
# - Your OpenAI API key (or other LLM provider)
# - Swiftlet MCP server URL and port
```

### 4.4 Run the Agent
```bash
python main.py
# Or whatever entry point your team uses
```

## Step 5: Development Workflow

### 5.1 Iterative Development
1. **Edit Grasshopper clusters** → define/modify tools
2. **Test in LM Studio/Claude** → verify tool behavior
3. **Update Python agent** → add reasoning logic
4. **Test end-to-end** → agent calls tools autonomously

### 5.2 Version Control
```bash
# Regular commits in your team branch
git add team_XX/
git commit -m "Add new tool: <description>"
git push origin team_XX
```

### 5.3 Weekly Pull Request
- **Every Sunday by 11:59 PM Barcelona time**
- Create PR from `team_XX` → `main`
- Only include changes in your `team_XX/` folder
- Instructors review and merge

## Step 6: Coordination

- **Talk to other teams** — avoid duplicate tools
- **Document your tools** — clear descriptions help everyone
- **Ask instructors** — Scott for Grasshopper/MCP questions

---

# Common Troubleshooting

| Issue | Solution |
|-------|----------|
| Port mismatch | Check Grasshopper panel, update `mcp.json` |
| Tool not found | Verify name matches in definition & result clusters |
| Agent can't connect | Ensure Swiftlet server is running in Grasshopper |
| Merge conflicts | Only edit files in your `team_XX/` folder |

---

# Quick Reference

**Your team folder:** `team_XX/`  
**Grasshopper files:** `team_XX/gh/`  
**Python agent:** `team_XX/python/`  
**MCP config:** `mcp.json` (root)  
**Weekly deadline:** Sunday 11:59 PM Barcelona  
**Contact:** Scott (Grasshopper/MCP), Instructors (general)
