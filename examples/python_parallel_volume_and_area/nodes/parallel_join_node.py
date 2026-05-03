from __future__ import annotations

from nodes.routing import WorkflowState


def wait_for_parallel_join_node(state: WorkflowState) -> WorkflowState:
    '''
    This node is a safe sink for each parallel branch in multi-domain mode.

    Why it exists:
    - In multi-domain routes, each branch should finish quietly until all
      selected domains are complete.
    - Using this sink avoids accidentally triggering combine early.
    '''

    # Return no state updates. This node is only a parking place for branches
    # while per-domain conditional routing decides when combine can run.
    return {}
