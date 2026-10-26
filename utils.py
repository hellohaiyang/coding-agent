import json
import os
from datetime import datetime
from pathlib import Path
from Agent.config.config import Config

class ModelOutputFormatError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def write_log(message, log_file_name=Path(Config.run_workspace) / "agents.log"):
    log_file_name = Path(log_file_name)
    log_file_name.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file_name, "a", encoding="utf-8") as f:
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{time}] {message}\n")
        f.write(f"\n\n")


def agent_print(content, mode=1):
    # mode=1仅记录日志
    # mode=2记录日志+打印到控制台
    write_log(content)
    if mode == 2:
        print(content)


def valid_llm_response(llm_response):
    if llm_response is None:
        raise ModelOutputFormatError(
            "empty_response",
            "模型响应为空",
        )
    content = getattr(llm_response, "content", None)
    tool_calls = getattr(llm_response, "tool_calls", None) or []
    if not tool_calls:
        if not isinstance(content, str) or not content.strip():
            raise ModelOutputFormatError(
                "empty_content",
                "模型既没有返回工具调用，也没有返回有效文本",
            )
        return
    for index, tool_call in enumerate(tool_calls):
        tool_call_id = getattr(tool_call, "id", None)
        function = getattr(tool_call, "function", None)
        if not tool_call_id or function is None:
            raise ModelOutputFormatError(
                "invalid_tool_call",
                f"第 {index + 1} 个工具调用缺少 id 或 function",
            )
        tool_name = getattr(function, "name", None)
        arguments_json = getattr(function, "arguments", None)
        if not tool_name or not isinstance(arguments_json, str):
            raise ModelOutputFormatError(
                "invalid_tool_call",
                f"第 {index + 1} 个工具调用缺少名称或参数",
            )
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as error:
            raise ModelOutputFormatError(
                "invalid_tool_arguments_json",
                (
                    f"工具 {tool_name} 参数不是合法 JSON："
                    f"{error.msg}"
                ),
            ) from error
        if not isinstance(arguments,dict):
            raise ModelOutputFormatError(
                "invalid_tool_arguments",
                f"工具 {tool_name} 参数必须是 JSON 对象",
            )

def dump_llm_response(llm_response):
    if hasattr(llm_response,"model_dump_json"):
        raw_output=llm_response.model_dump_json()
    else:
        raw_output=str(llm_response)
    return raw_output[:4000]

