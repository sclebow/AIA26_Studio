"""backend.nodes.site_optimizer — re-export of the live optimization runtime
(connection.notebook_logic.view_optimization_runtime) which drives the NSGA-II
site/view optimizer. One backend, no duplicate logic."""
from connection.notebook_logic.view_optimization_runtime import *  # noqa: F401,F403
from connection.notebook_logic import view_optimization_runtime as _impl  # noqa: F401
