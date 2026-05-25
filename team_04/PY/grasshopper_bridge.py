"""
Grasshopper Bridge - Send generated shapes to Grasshopper via MCP

This module handles the integration between the Shape Generator and Grasshopper,
including:
- Converting shapes to Grasshopper-compatible format
- Sending shapes via MCP tool calls
- Receiving feedback and updating parameters
- Managing multiple shape iterations

Usage:
    from grasshopper_bridge import GrasshopperBridge
    
    bridge = GrassopperBridge(mcp_client)
    result = bridge.send_shape(shape_output)
    feedback = bridge.get_shape_feedback(shape_id)
"""

from __future__ import annotations

import json
from typing import Any, Optional
from shape_generator_node import ShapeOutput
from mcp_client import McpClient


class GrassopperBridge:
    """
    Bridge for communicating with Grasshopper via MCP.
    
    Handles shape transmission, parameter updates, and feedback collection.
    """

    def __init__(self, mcp_client: McpClient):
        """
        Initialize Grasshopper bridge.
        
        Args:
            mcp_client: McpClient instance for MCP communication
        """
        self.mcp_client = mcp_client
        self.sent_shapes: dict[str, dict[str, Any]] = {}
        self.shape_feedback: dict[str, dict[str, Any]] = {}

    def send_shape(
        self,
        shape: ShapeOutput,
        tool_name: str = "parametric_shape_generator",
    ) -> str:
        """
        Send a generated shape to Grasshopper via MCP.
        
        Args:
            shape: ShapeOutput object with geometry
            tool_name: MCP tool name to call
            
        Returns:
            Tool result/response from Grasshopper
        """
        # Prepare MCP call arguments
        arguments = {
            "tool_name": tool_name,
            "shape_id": shape.shape_id,
            "input": {
                "shape_type": shape.shape_type,
                "parameters": shape.metadata,
            },
            "output": {
                "live_geometry": {
                    "geometry_type": "closed_polyline_footprint_3d",
                    "vertices_2d": shape.vertices_2d,
                    "vertices_3d": shape.vertices_3d,
                    "faces": shape.faces,
                },
                "shape_metadata": shape.metadata,
                "editable_parameters": shape.editable_parameters,
            },
        }

        # Cache the shape
        self.sent_shapes[shape.shape_id] = arguments

        # Call MCP tool
        try:
            result = self.mcp_client.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to send shape {shape.shape_id} to Grasshopper: {str(e)}")

    def send_shapes_batch(
        self,
        shapes: list[ShapeOutput],
        tool_name: str = "site_geometry_generator",
    ) -> str:
        """
        Send multiple shapes to Grasshopper as batch.
        
        Args:
            shapes: List of ShapeOutput objects
            tool_name: MCP tool name for batch operation
            
        Returns:
            Tool result from Grasshopper
        """
        batch_data = {
            "site_id": "BATCH_" + shapes[0].shape_id if shapes else "EMPTY",
            "buildings": [
                {
                    "shape_id": shape.shape_id,
                    "shape_type": shape.shape_type,
                    "geometry": {
                        "vertices_2d": shape.vertices_2d,
                        "vertices_3d": shape.vertices_3d,
                        "faces": shape.faces,
                    },
                    "metadata": shape.metadata,
                    "editable_parameters": shape.editable_parameters,
                }
                for shape in shapes
            ],
        }

        try:
            result = self.mcp_client.call_tool(tool_name, batch_data)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to send batch to Grasshopper: {str(e)}")

    def request_shape_modification(
        self,
        shape_id: str,
        parameters: dict[str, Any],
        tool_name: str = "modify_parametric_shape",
    ) -> str:
        """
        Request modification of a shape in Grasshopper.
        
        Args:
            shape_id: ID of shape to modify
            parameters: Modified parameters
            tool_name: MCP tool name for modification
            
        Returns:
            Modified shape from Grasshopper
        """
        if shape_id not in self.sent_shapes:
            raise ValueError(f"Shape {shape_id} not found in sent shapes cache")

        modification_request = {
            "shape_id": shape_id,
            "modifications": parameters,
        }

        try:
            result = self.mcp_client.call_tool(tool_name, modification_request)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to modify shape {shape_id}: {str(e)}")

    def get_shape_feedback(self, shape_id: str) -> Optional[dict[str, Any]]:
        """
        Get feedback from Grasshopper for a shape.
        
        Args:
            shape_id: ID of shape to get feedback for
            
        Returns:
            Feedback dictionary or None if not available
        """
        return self.shape_feedback.get(shape_id)

    def store_feedback(
        self,
        shape_id: str,
        feedback: dict[str, Any],
    ) -> None:
        """
        Store feedback received from Grasshopper.
        
        Args:
            shape_id: ID of shape feedback is for
            feedback: Feedback data
        """
        self.feedback[shape_id] = feedback

    def validate_shape_geometry(self, shape: ShapeOutput) -> bool:
        """
        Validate shape geometry before sending to Grasshopper.
        
        Args:
            shape: ShapeOutput to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check vertices count
        if len(shape.vertices_2d) < 3:
            return False

        # Check for duplicate vertices
        seen = set()
        for vertex in shape.vertices_2d:
            v_tuple = tuple(vertex)
            if v_tuple in seen:
                return False
            seen.add(v_tuple)

        # Check 3D consistency
        if len(shape.vertices_3d) != 2 * len(shape.vertices_2d):
            return False

        # Check metadata
        if "area" not in shape.metadata or shape.metadata["area"] <= 0:
            return False

        if "height" not in shape.metadata or shape.metadata["height"] <= 0:
            return False

        return True

    def export_shape_for_grasshopper(self, shape: ShapeOutput) -> str:
        """
        Export shape as formatted JSON for direct Grasshopper input.
        
        Args:
            shape: ShapeOutput to export
            
        Returns:
            JSON string formatted for Grasshopper
        """
        gh_format = {
            "shape_id": shape.shape_id,
            "shape_type": shape.shape_type,
            "geometry": {
                "footprint_2d": shape.vertices_2d,
                "extrusion_3d": shape.vertices_3d,
                "brep_faces": shape.faces,
            },
            "parameters": {
                "metadata": shape.metadata,
                "editable": shape.editable_parameters,
            },
        }

        return json.dumps(gh_format, indent=2)


class ShapeModificationRequest:
    """Request for modifying a shape."""

    def __init__(self, shape_id: str):
        """Initialize modification request."""
        self.shape_id = shape_id
        self.modifications: dict[str, Any] = {}

    def set_parameter(self, param_name: str, value: Any) -> ShapeModificationRequest:
        """Set a parameter modification."""
        self.modifications[param_name] = value
        return self

    def set_height(self, new_height: float) -> ShapeModificationRequest:
        """Set new height."""
        return self.set_parameter("height", new_height)

    def set_length(self, new_length: float) -> ShapeModificationRequest:
        """Set new length."""
        return self.set_parameter("length", new_length)

    def set_width(self, new_width: float) -> ShapeModificationRequest:
        """Set new width."""
        return self.set_parameter("width", new_width)

    def set_rotation(self, angle_degrees: float) -> ShapeModificationRequest:
        """Set rotation angle."""
        return self.set_parameter("rotation_angle", angle_degrees)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "shape_id": self.shape_id,
            "modifications": self.modifications,
        }
