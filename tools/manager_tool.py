import asyncio

import inspect
from functools import partial

from pathlib import Path

from pydantic import ValidationError

from Agent.config.config import Config
from Agent.tools.tool_bash import BASH_SCHEMA
from Agent.tools.tool_crewai import build_crewai_tools
from Agent.tools.tool_read import READ_SCHEMA
from Agent.tools.tool_edit import EDIT_SCHEMA
from Agent.tools.tool_validation import TOOL_ARGUMENT_MODELS
from Agent.tools.tool_write import WRITE_SCHEMA
from Agent.tools.tool_bash import bash
from Agent.tools.tool_read import read
from Agent.tools.tool_edit import edit
from Agent.tools.tool_write import write
from Agent.utils import agent_print
from Agent.tools.tool_subagents import (
    run_subagent,
    run_parallel_agents,
    run_agent_team,
    SUBAGENT_SCHEMA,
    PARALLEL_AGENTS_SCHEMA,
    AGENT_TEAM_SCHEMA,
)
from Agent.tools.tool_memory import MEMORY_SCHEMAS

SUBAGENT_HANDLERS = {
    "run_subagent": run_subagent,
    "run_parallel_agents": run_parallel_agents,
    "run_agent_team": run_agent_team,
}
TOOLS_SCHEMA = [
    BASH_SCHEMA,
    READ_SCHEMA,
    WRITE_SCHEMA,
    EDIT_SCHEMA,
    SUBAGENT_SCHEMA,
    PARALLEL_AGENTS_SCHEMA,
    AGENT_TEAM_SCHEMA,
    *MEMORY_SCHEMAS,
]


class ManagerTools:
    def __init__(self, agent_workspace, sandbox, system_prompt, skill_path):
        self.system_prompt = system_prompt
        self.skill_path = Path(skill_path).resolve()
        self.agent_workspace = agent_workspace
        self.sandbox = sandbox
        self.tools = {
            "bash": partial(bash, sandbox=self.sandbox),
            "read": read,
            "edit": edit,
            "write": write,
        }
        self.sandbox = sandbox
        # self.auto_check = AutoCheckTools()
        self.semaphore = asyncio.Semaphore(10)
        self.mutation_lock = asyncio.Lock()
        self.mcp = None
        # crewai
        self.subagent_semaphore = asyncio.Semaphore(2)
        self.tools.update({
            name: partial(self.run_crewai, handler)
            for name, handler in SUBAGENT_HANDLERS.items()
        })
        #
        self.skill_reads = []
        self.mcp_calls = []

    async def execute_handler(self, handler, arguments):
        if inspect.iscoroutinefunction(handler):  # 如果是异步函数，直接await
            return await handler(**arguments)

        return await asyncio.to_thread(handler, **arguments)  # 如果是同步函数，放另一个线程执行

    async def run_tool(self, tool_name, arguments):
        # mcp
        if self.mcp is not None and tool_name in self.mcp.tools:
            async with self.semaphore:
                async with self.mutation_lock:
                    if Config.tool_mode == "manual":
                        answer = await asyncio.to_thread(input, f"执行 MCP 工具：{tool_name}\n"
                                                                f"参数：{arguments}\n输入yes:")
                        if answer.strip() != "yes":
                            return {
                                "success": False,
                                "output": None,
                                "error": "用户拒绝了该工具的执行",
                            }
                    result = await self.mcp.run_tool(
                        tool_name, arguments
                    )
                    self.mcp_calls.append({
                        "name": tool_name,
                        "success": result["success"],
                    })
                    return result
        # 1.判断工具是否存在
        if tool_name not in self.tools:
            return {
                "success": False,
                "output": None,
                "error": str("未知工具"),
            }
        # 参数校验
        try:
            arguments = (TOOL_ARGUMENT_MODELS[tool_name].model_validate(arguments).model_dump())
        except ValidationError as error:
            first_error = error.errors()[0]
            field = ".".join(
                str(part)
                for part in first_error["loc"]
            )
            message = first_error["msg"]
            return {
                "success": False,
                "output": None,
                "error": f"参数错误 {field}: {message}",
            }

        # 2.判断工具的安全性
        if Config.tool_mode == "manual":
            check_ans = input(f"执行工具，是否允许。\n{tool_name}\n{arguments}\n输入yes:")
            if check_ans != "yes":
                return {
                    "success": False,
                    "output": None,
                    "error": str("用户拒绝了该工具的执行"),
                }
        if Config.tool_mode == "auto":
            # check_ans = self.auto_check.run_auto_check(tool_name, arguments)
            # 取消三层工具审批的判断。因为bash执行在docker中，而且小模型+大模型带来的延迟过高，不值。
            check_ans = True
            if not check_ans:
                return {
                    "success": False,
                    "output": None,
                    "error": str("自动审批拒绝了该工具的执行"),
                }
        # 3.参数校验
        valid_ans = self.valid_arguments(tool_name, arguments)
        if valid_ans != "ok":
            return {
                "success": False,
                "output": None,
                "error": str(valid_ans),
            }
        agent_print(f"执行工具{tool_name}\n{arguments}\n", 2)
        # result = self.tools[tool_name](**arguments)
        handler = self.tools[tool_name]
        try:
            if tool_name in SUBAGENT_HANDLERS:
                raw_result = await self.execute_handler(handler, arguments)
            else:
                async with self.semaphore:
                    if tool_name in {
                        "write",
                        "edit",
                        "bash",
                        "writememory",
                        "editmemory",
                    }:
                        async with self.mutation_lock:
                            raw_result = await self.execute_handler(handler, arguments)
                    else:
                        raw_result = await self.execute_handler(handler, arguments)
        except Exception as error:
            return {
                "success": False,
                "output": None,
                "error": str(error),
            }
        # bash 非零退出码
        if tool_name == "bash":
            if raw_result.get("exit_code") != 0:
                return {
                    "success": False,
                    "output": raw_result,
                    "error": (
                            raw_result.get("stderr")
                            or f"命令退出码：{raw_result.get('exit_code')}"
                    ),
                }
            return {
                "success": True,
                "output": raw_result,
                "error": None,
            }
        # 兼容现有 read/write/edit 的错误字符串
        if (
                isinstance(raw_result, str)
                and raw_result.lower().startswith("error")
        ):
            return {
                "success": False,
                "output": None,
                "error": raw_result,
            }
        if tool_name == "read":
            path = Path(arguments["path"]).expanduser().resolve()
            if (
                    path.is_relative_to(self.skill_path)
                    and path.name == "SKILL.md"
            ):
                self.skill_reads.append({
                    "path": str(path),
                    "offset": arguments.get("offset", 1),
                    "limit": arguments.get("limit", 200),
                })
        return {
            "success": True,
            "output": raw_result,
            "error": None,
        }

    def valid_arguments(self, tool_name, arguments):
        if tool_name == "bash":
            command = arguments.get("command")
            timeout = arguments.get("timeout", 30)
            if not command.strip():
                return "bash command 必须是非空字符串"
            if not isinstance(timeout, int) or timeout < 1 or timeout > Config.sandbox_max_timeout:
                return (
                    f"bash timeout 必须是 1 到 "
                    f"{Config.sandbox_max_timeout} 之间的整数"
                )
            return "ok"
        if tool_name not in {"read", "write", "edit"}:
            return "ok"
        path = Path(arguments["path"]).expanduser().resolve()
        source_workspace = Path(Config.workspace).expanduser().resolve()
        agent_workspace = Path(self.agent_workspace).expanduser().resolve()
        in_source_workspace = (path == source_workspace or source_workspace in path.parents)
        in_agent_workspace = (path == agent_workspace or agent_workspace in path.parents)
        if tool_name == "read":
            in_skill_workspace = False
            if Config.skills_enabled:
                skill_workspace = self.skill_path
                in_skill_workspace = path.is_relative_to(skill_workspace)
            if not (in_skill_workspace or in_source_workspace or in_agent_workspace):
                return "read 只能读取用户源目录或 Agent 工作副本或skill"
        if tool_name in {"edit", "write"}:
            if not in_agent_workspace:
                return "write 和 edit 只能修改 Agent 工作副本"
        return "ok"

    async def run_crewai(self, handler, **arguments):
        arguments["context"] = (
            f"{self.system_prompt}\n\n"
            f"源目录只允许读取：{Config.workspace}\n"
            f"宿主机工作副本：{self.agent_workspace}\n"
            "read、write、edit 使用宿主机绝对路径。\n"
            "bash 使用容器路径 /workspace。\n\n"
            f"主 Agent 提供的背景与本次要求：\n"
            f"{arguments.get('context', '')}"
        )

        async with self.subagent_semaphore:
            tools = build_crewai_tools(self)
            return await asyncio.to_thread(
                handler,
                **arguments,
                tools=tools,
            )
