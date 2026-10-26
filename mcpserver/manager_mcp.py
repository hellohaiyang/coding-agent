import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from Agent.config.config import Config
from Agent.tools.tool_mcp import MCPTools


def create_transport(evolution, agent_workspace):
    if Config.mcp_mode == "local":
        server_path = (
            Path(Config.evolution_root) / "mcp_server.py"
        ).resolve()
        tools_path = evolution.tools_path.resolve()
        workspace = Path(agent_workspace).resolve()
        if not server_path.is_file():
            raise FileNotFoundError(
                f"MCP 服务入口不存在：{server_path}"
            )
        if not tools_path.is_dir():
            raise FileNotFoundError(
                f"MCP 工具目录不存在：{tools_path}"
            )
        if not workspace.is_dir():
            raise FileNotFoundError(
                f"任务工作目录不存在：{workspace}"
            )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-B",
                "-u",
                str(server_path),
                "--tools-dir",
                str(tools_path),
            ],
            cwd=str(workspace),
        )
        return stdio_client(parameters)
    if Config.mcp_mode == "remote":
        url = Config.mcp_url.strip()
        if not url:
            raise ValueError("启用远程 MCP 时必须配置 mcp_url")
        return streamable_http_client(url)
    raise ValueError(f"未知的 MCP 模式：{Config.mcp_mode}")


@asynccontextmanager
async def connect_mcp(manager_tool, evolution, agent_workspace):
    manager_tool.mcp = None
    if not Config.mcp_enabled:
        yield
        return
    transport = create_transport(evolution, agent_workspace)

    async with transport as streams:
        read, write = streams[:2]
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timedelta(seconds=60),
        ) as session:
            await session.initialize()
            mcp_tools = MCPTools(session)
            await mcp_tools.load_tools()
            manager_tool.mcp = mcp_tools
            try:
                yield
            finally:
                manager_tool.mcp = None