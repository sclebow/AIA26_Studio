from shape_generator_node import ShapeGenerator
from grasshopper_bridge import GrasshopperBridge


class MockMcpClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, name: str, arguments: dict):
        print(f"MockMcpClient.call_tool invoked: name={name}")
        print("arguments:")
        import json

        print(json.dumps(arguments, indent=2))
        self.calls.append((name, arguments))
        return "MOCK_OK"


def main():
    gen = ShapeGenerator()
    shape = gen.generate_rectangle(length=80, width=12, height=12)

    mock = MockMcpClient()
    bridge = GrasshopperBridge(mock)

    result = bridge.send_shape(shape, tool_name="parametric_shape_generator_04")
    print("bridge.send_shape result:", result)


if __name__ == "__main__":
    main()
