import os
from pathlib import Path
from Agent.config.config import Config
from Agent.utils import agent_print


def load_agents_md(pwd=Config.workspace):
    agents_md = []
    agents_md_path = Path(pwd) / "AGENTS.md"
    if agents_md_path.exists():
        agents_md.append(agents_md_path.read_text(encoding="utf-8"))
        agent_print("agents.md read ok", mode=2)
    claude_md_path = Path(pwd) / "CLAUDE.md"
    if claude_md_path.exists():
        agents_md.append(claude_md_path.read_text(encoding="utf-8"))
        agent_print("claude.md read ok", mode=2)
    return str(agents_md)


def load_environments():
    env = "当前环境如下：\n"
    env += f"workspace:{Config.workspace}\n"
    env += "这个 workspace 是用户源代码目录，只允许读取，禁止修改。\n"
    env += f"platform:{os.name}\n"
    # env += f"\n所有历史消息文件，可以用grep命令查找，防止压缩丢失重要信息。文件路径：{Config.history_path}\n"
    return env


def load_skills(pwd=Config.workspace):
    skills_description = """
    以下是skills的名称和简要描述。
    如果要查看详情，可以使用读工具读取具体的skills。
    """
    root = Path(pwd)
    for path in root.rglob("SKILL.md"):
        lines = path.read_text(encoding="utf-8").splitlines()[:5]
        skills_description += f"\n文件：{path.resolve()}\n"
        skills_description += "\n".join(lines) + "\n"
    return skills_description

# print(load_agents_md())
# print(load_environments())
