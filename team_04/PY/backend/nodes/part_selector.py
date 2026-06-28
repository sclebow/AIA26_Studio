"""backend.nodes.part_selector — re-export of the live implementation in
connection.notebook_logic.part_selector (one backend, no duplicate logic)."""
from connection.notebook_logic.part_selector import *  # noqa: F401,F403
from connection.notebook_logic import part_selector as _impl  # noqa: F401
