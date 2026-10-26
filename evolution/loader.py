import json
import re
from dataclasses import dataclass
from pathlib import Path
import shutil
from Agent.config.config import Config


@dataclass(frozen=True)
class EvolutionVersion:
    version: str
    root: Path
    memory_path: Path
    skills_path: Path
    prompt_path: Path
    tools_path: Path


def load_version(version=None):
    """读取当前版本，或明确指定的版本。"""
    base = Path(Config.evolution_root).resolve()

    if version is None:
        data = json.loads(
            (base / "version.json").read_text(encoding="utf-8")
        )
        version = data["current"]

    if (
        not isinstance(version, str)
        or re.fullmatch(r"v[1-9]\d*", version) is None
    ):
        raise ValueError(f"无效的进化版本：{version!r}")

    root = (base / version).resolve()
    if not root.is_relative_to(base):
        raise ValueError("版本目录不能超出 evolution")

    for name in ("memory", "skills", "prompt", "tools"):
        path = root / name
        if not path.is_dir():
            raise FileNotFoundError(f"版本资源目录不存在：{path}")
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"版本资源目录越界：{path}")

    if not (root / "prompt" / "system.md").is_file():
        raise FileNotFoundError(
            f"版本缺少系统提示词：{root / 'prompt' / 'system.md'}"
        )

    return EvolutionVersion(
        version=version,
        root=root,
        memory_path=root / "memory",
        skills_path=root / "skills",
        prompt_path=root / "prompt",
        tools_path=root / "tools",
    )


def load_run_version(agent_workspace, recovery=False, version=None):
    """新任务记录版本，恢复任务读取原版本。"""
    workspace = Path(agent_workspace).resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"任务工作目录不存在：{workspace}")

    record_path = workspace.parent / "evolution.json"

    if recovery:
        if not record_path.is_file():
            raise FileNotFoundError(
                f"任务缺少版本记录，不能确定原版本：{record_path}"
            )

        data = json.loads(record_path.read_text(encoding="utf-8"))
        saved_version = data["version"]

        if not isinstance(saved_version, str):
            raise ValueError(f"任务版本记录无效：{record_path}")

        if version is not None and version != saved_version:
            raise ValueError(
                f"恢复任务必须使用原版本：{saved_version}"
            )

        return load_version(saved_version)

    selected = load_version(version)

    # 使用 x，避免覆盖同一任务已经存在的版本记录。
    with record_path.open("x", encoding="utf-8") as file:
        json.dump({"version": selected.version}, file, indent=2)

    return selected


def prepare_run_memory(evolution, agent_workspace, recovery=False):
    """新任务复制版本记忆，恢复任务使用已有副本。"""
    target = Path(agent_workspace).resolve().parent / "memory"
    if recovery:
        if not target.is_dir():
            raise FileNotFoundError(f"任务记忆副本不存在：{target}")
        return target
    shutil.copytree(
        evolution.memory_path,
        target,
        ignore=shutil.ignore_patterns(
            "*.db", "*.db-*",
            "*.sqlite", "*.sqlite-*",
            "*.sqlite3", "*.sqlite3-*",
        ),
    )
    return target