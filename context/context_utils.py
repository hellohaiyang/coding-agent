import os
from pathlib import Path

import yaml

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


def load_skills(pwd):
    if not Config.skills_enabled:
        return ""
    root = Path(pwd).expanduser().resolve()
    descriptions = []
    names = set()
    for path in sorted(root.rglob("SKILL.md")):
        path = path.resolve()
        if not path.is_relative_to(root):
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            if not lines or lines[0].strip() != "---":
                raise ValueError("缺少 YAML 元数据")

            end = next(
                i for i in range(1, len(lines))
                if lines[i].strip() == "---"
            )
            metadata = yaml.safe_load("\n".join(lines[1:end]))
            if not isinstance(metadata, dict):
                raise ValueError("元数据必须是字典")
            name = metadata.get("name")
            description = metadata.get("description")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name 必须是非空字符串")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("description 必须是非空字符串")
            if name in names:
                raise ValueError(f"技能名称重复：{name}")
            names.add(name)
            descriptions.append(
                f"名称：{name}\n"
                f"用途：{description}\n"
                f"文件：{path}"
            )
        except (
            OSError, UnicodeError, ValueError,
            StopIteration, yaml.YAMLError,
        ) as error:
            agent_print(f"跳过无效技能 {path}：{error}", mode=2)
    if not descriptions:
        return "\n当前没有可用技能。\n"
    return "\n可用技能目录：\n\n" + "\n\n".join(descriptions) + "\n"

# print(load_agents_md())
# print(load_environments())
