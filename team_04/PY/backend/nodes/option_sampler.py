"""backend.nodes.option_sampler — re-export of the live implementation in
connection.notebook_logic.option_sampler (one backend, no duplicate logic)."""
from connection.notebook_logic.option_sampler import *  # noqa: F401,F403
from connection.notebook_logic import option_sampler as _impl  # noqa: F401
