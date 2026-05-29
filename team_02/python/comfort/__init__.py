"""
comfort/ — local comfort computation, migrated out of Grasshopper.

These three functions were previously Python scripts running inside GH clusters
and reached over an MCP/HTTP bridge. They are pure Python over the layout JSON
(no Rhino geometry kernel), so they now live in-process. The agent reaches them
through LocalToolClient, which preserves the old McpClient.call_tool() interface.

Reference originals: studio/code inside gh clusters for tools/
"""

from comfort.compute_comfort_scores import compute_comfort_scores
from comfort.detect_sensorial_conflicts import detect_sensorial_conflicts
from comfort.generate_suggestions import generate_suggestions

__all__ = [
    "compute_comfort_scores",
    "detect_sensorial_conflicts",
    "generate_suggestions",
]
