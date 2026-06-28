"""backend.nodes.shape_inference — re-export of the live implementation in
connection.notebook_logic.shape_inference (one backend, no duplicate logic)."""
from connection.notebook_logic.shape_inference import *  # noqa: F401,F403
from connection.notebook_logic import shape_inference as _impl  # noqa: F401
