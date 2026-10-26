import asyncio
import json

from crewai.tools import tool


def build_crewai_tools(manager_tool):
    loop = asyncio.get_running_loop()

    def execute(name, arguments):
        future = asyncio.run_coroutine_threadsafe(
            manager_tool.run_tool(name, arguments),
            loop,
        )
        return json.dumps(future.result(), ensure_ascii=False)

    @tool("bash")
    def crewai_bash(command: str, timeout: int = 30) -> str:
        """在 Docker 中执行命令，工作目录为 /workspace，使用容器路径。"""
        return execute("bash", {
            "command": command,
            "timeout": timeout,
        })

    @tool("read")
    def crewai_read(
            path: str,
            offset: int = 1,
            limit: int = 200,
    ) -> str:
        """读取宿主机文本文件，path 使用绝对路径，offset 从 1 开始。"""
        return execute("read", {
            "path": path,
            "offset": offset,
            "limit": limit,
        })

    @tool("write")
    def crewai_write(path: str, content: str) -> str:
        """写入文本文件，只能使用 Agent 工作副本的宿主机绝对路径。"""
        return execute("write", {
            "path": path,
            "content": content,
        })

    @tool("edit")
    def crewai_edit(
            path: str,
            old_text: str,
            new_text: str,
    ) -> str:
        """替换文件中唯一匹配的文本，只能使用工作副本的宿主机绝对路径。"""
        return execute("edit", {
            "path": path,
            "old_text": old_text,
            "new_text": new_text,
        })

    return [crewai_bash, crewai_read, crewai_write, crewai_edit]
