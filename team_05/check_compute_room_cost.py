import json
from team_05.python._runtime.config import load_settings
from team_05.python._runtime.mcp_client import McpClient

settings = load_settings()
client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
client.initialize()
tools = client.list_tools()

print("=" * 80)
print("DETAILED TOOL ANALYSIS")
print("=" * 80)

for t in tools:
    name = t.get('name', '<unknown>')
    if 'compute_room_cost' in name.lower() or 'space' in name.lower():
        print(f"\n✓ TOOL: {repr(name)}")
        print(f"  Description: {t.get('description', 'N/A')}")
        print(f"\n  Input Schema:")
        schema = t.get('inputSchema', {})
        print(json.dumps(schema, indent=4))
        print("\n" + "-" * 80)
