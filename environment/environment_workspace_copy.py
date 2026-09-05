import os
import shutil
from pathlib import Path
from uuid import uuid4

from Agent.config.config import Config
from Agent.environment.environment_workspace_changes import create_baseline


def create_work_space_copy(source_workspace, run_id):
    source = Path(source_workspace).expanduser().resolve()
    if not source.exists():
        raise ValueError(f"workspace目录不存在{source}")
    if not source.is_dir():
        raise ValueError(f"不是目录{source}")
    runs_root = Config.run_workspace
    target_root = runs_root / run_id / "workspace"
    target_root.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, target_root, symlinks=True)
    create_baseline(target_root)
    return target_root
