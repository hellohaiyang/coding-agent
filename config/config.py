import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    api = os.getenv("DEEPSEEK_API_KEY")
    model_name = "deepseek"  # 使用的api的大模型的名称
    # workspace = r"D:\PythonProject\finalagent\workspace"
    max_step = 100  # 最大步数
    max_tokens = 5000000  # 累计token不能超
    tool_mode = "auto"  # 工具是自动审批还是人工？
    max_content_token = 120000  # 上下文最大长度
    context_safe_size = 80000  # 上下文安全性，压缩到这个之下
    tool_trim_size = 80000  # 比较长就进行工具压缩
    tool_max_output = 30000  # 工具的最大长度，超过就截断
    tool_max_attempts = 3  # 工具最大尝试次数
    max_summary_chars=10000#限制摘要字数
    max_consecutive_tool_failures = 5  #
    max_model_format_retries = 2  #
    skill_path = r"Agent/skills"  # skill的存放目录
    max_size_long_term_memory = 5000  # 如果长期记忆太长，超过5000字就截断
    qwen_check_model_path = "/data/shenghaiyang/downloadmodel/qwen2coder/"  # 自动审批的小模型目录

    workspace = "/home/shenghaiyang/agentproject/workspace/"  # input("workspace:")  # 工作目录
    run_workspace = (
            Path.home() / ".codeagent" / "runs"
    ).resolve()
    # long_term_memory_path = Path(run_workspace) / "long_memory.md"  # 存长期记忆的文件
    run_id_interrupt_path = Path(run_workspace) / "run_id.txt"
    # history_path = Path(run_workspace) / "history_messages.json"  # 存所有对话历史的文件，防止压缩丢信息
    # docker
    sandbox_image = "codeagent-sandbox-python:latest"
    sandbox_memory = "1g"
    sandbox_cpus = "1"
    sandbox_pids_limit = "256"
    sandbox_max_timeout = 300
    #
    user_long_term_memory = Path(run_workspace) / "user_long_memory.md"

    @classmethod
    def get_project_long_term_memory_path(cls, run_id):
        return Path(cls.run_workspace) / run_id / "project_long_memory.md"
