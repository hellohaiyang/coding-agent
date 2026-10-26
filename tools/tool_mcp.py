import re
from jsonschema import validate


class MCPTools:
    def __init__(self, client):
        self.client = client
        self.tools = {}
        self.schemas = []

    async def load_tools(self):
        cursor = None
        while True:
            page = await self.client.list_tools(cursor=cursor)
            for tool in page.tools:
                name = f"mcp__{tool.name}"
                self.tools[name] = tool
                self.schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description or tool.name,
                        "parameters": tool.inputSchema,
                    },
                })
            cursor = page.nextCursor
            if cursor is None:
                break

    async def run_tool(self, name, arguments):
        try:
            tool = self.tools[name]
            validate(arguments, tool.inputSchema)
            result = await self.client.call_tool(tool.name, arguments)
            parts = []
            for block in result.content:
                if block.type == "text":
                    parts.append(block.text)
                else:
                    parts.append(f"[暂不展示 {block.type} 内容]")
            text = "\n".join(parts)
            return {
                "success": not result.isError,
                "output": {
                    "text": text,
                    "structured_content": result.structuredContent,
                },
                "error": (
                        text or "MCP 工具执行失败"
                ) if result.isError else None,
            }
        except Exception as error:
            return {
                "success": False,
                "output": None,
                "error": str(error),
            }
