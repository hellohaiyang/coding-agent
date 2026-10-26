from datetime import datetime
from uuid import uuid4
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("LocalFastServer")


@mcp.tool()
def generate_uuid() -> str:
    """生成一个随机的 UUID v4 字符串。"""
    return str(uuid4())


@mcp.tool()
def get_system_time() -> str:
    """获取服务器当前系统时间，包含本地时区偏移。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


if __name__ == "__main__":
    mcp.run(transport="stdio")
