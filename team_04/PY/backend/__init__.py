"""Compatibility package exposing the requested backend.nodes.* import paths.

The single, live implementation lives in connection/notebook_logic/* (one
backend — see ARCHITECTURE notes). These modules re-export it so the requested
`backend/nodes/<module>.py` paths exist and resolve to the SAME code, with no
duplicate algorithms.
"""
