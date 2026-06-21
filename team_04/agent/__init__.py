__all__ = ["build_agent_graph", "run_agent"]


def build_agent_graph(*args, **kwargs):
	from .graph import build_agent_graph as _build_agent_graph

	return _build_agent_graph(*args, **kwargs)


def run_agent(*args, **kwargs):
	from .graph import run_agent as _run_agent

	return _run_agent(*args, **kwargs)