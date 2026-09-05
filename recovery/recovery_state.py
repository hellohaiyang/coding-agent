from enum import Enum
from typing import Optional

from dataclasses import dataclass

class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LIMIT_REACHED = "limit_reached"


class RunPhase(str, Enum):
    READY_FOR_LLM = "ready_for_llm"
    LLM_INFLIGHT = "llm_inflight"
    TOOLS_PENDING = "tools_pending"
    TOOLS_RUNNING = "tools_running"


class ToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass
class AgentState:
    run_id: str
    task: str
    status: RunStatus = RunStatus.CREATED
    phase: RunPhase = RunPhase.READY_FOR_LLM
    step: int = 0
    used_tokens: int = 0
    final_answer: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolCallState:
    run_id: str
    tool_call_id: str
    tool_name: str
    arguments_json: str
    status: ToolStatus = ToolStatus.PENDING
    result_json: Optional[str] = None
    error: Optional[str] = None
    attempt: int = 0
