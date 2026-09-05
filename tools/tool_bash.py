import subprocess

from Agent.config.config import Config


def bash(command: str, timeout: int = 30, sandbox=None):
    # try:
    #     process = subprocess.run(
    #         command,
    #         shell=True,
    #         capture_output=True,
    #         text=True,
    #         timeout=timeout,
    #         encoding='utf-8',
    #         cwd=workspace,
    #     )
    #     return {
    #         "stdout": process.stdout[:Config.tool_max_output],
    #         "stderr": process.stderr[:Config.tool_max_output],
    #         "exit_code": process.returncode,
    #     }
    # except subprocess.TimeoutExpired:
    #     return {
    #         "stdout": "",
    #         "stderr": f"timeout after {timeout} seconds",
    #         "exit_code": -1,
    #     }
    if sandbox is None:
        return {
            "stdout": "",
            "stderr": "Docker sandbox 未初始化",
            "exit_code": -1,
        }
    return sandbox.exec(command=command, timeout=timeout)


BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a shell command inside a Docker container. "
                       "The working directory is /workspace. "
                       "Host absolute paths are unavailable; use /workspace for project files.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command executed inside Docker. "
                                   "Use /workspace paths and never use host workspace paths.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds",
                    "minimum": 1,
                    "maximum": Config.sandbox_max_timeout,
                    "default": 30,
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}
