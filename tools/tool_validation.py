from pydantic import BaseModel, ConfigDict, Field, field_validator

from Agent.config.config import Config


class ToolArguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )


class BashArguments(ToolArguments):
    command: str = Field(min_length=1, max_length=20000)
    timeout: int = Field(
        default=30,
        ge=1,
        le=Config.sandbox_max_timeout,
    )

    @field_validator("command")
    @classmethod
    def command_not_blank(cls, value):
        if not value.strip():
            raise ValueError("command is none")
        return value


class ReadArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    offset: int = Field(default=1, ge=1)
    limit: int = Field(default=200, ge=1, le=2000)


class WriteArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1000000)


class EditArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    old_text: str = Field(min_length=1, max_length=1000000)
    new_text: str = Field(max_length=1000000)


class AgentTask(ToolArguments):
    role: str = Field(min_length=1)
    task: str = Field(min_length=1)


class SearchMemoryArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class SubagentArguments(ToolArguments):
    """委派一个专业子 Agent 完成独立任务。"""
    role: str = Field(min_length=1)
    task: str = Field(min_length=1)
    context: str = Field(
        default="",
        description="相关背景、本次用户要求和只读或修改限制。",
    )


class ParallelAgentsArguments(ToolArguments):
    """并行执行互相独立的任务；不要安排修改同一文件的任务。"""
    tasks: list[AgentTask] = Field(min_length=1, max_length=8)
    context: str = Field(
        default="",
        description="各任务共享的背景、本次用户要求和操作限制。",
    )


class AgentTeamArguments(ToolArguments):
    """组织多个专业成员协作，按成员顺序执行任务，可相互提问和委派。"""
    goal: str = Field(min_length=1)
    members: list[AgentTask] = Field(min_length=1, max_length=8)
    context: str = Field(
        default="",
        description="团队共享的背景、本次用户要求和操作限制。",
    )


TOOL_ARGUMENT_MODELS = {
    "bash": BashArguments,
    "read": ReadArguments,
    "write": WriteArguments,
    "edit": EditArguments,
    "search": SearchMemoryArguments,
    "readmemory": ReadArguments,
    "writememory": WriteArguments,
    "editmemory": EditArguments,
    "run_subagent": SubagentArguments,
    "run_parallel_agents": ParallelAgentsArguments,
    "run_agent_team": AgentTeamArguments,
}
