import hashlib
import json
import os
import shutil
from pathlib import Path

INTERNAL_FILES = {
    "agent_state.db",
    "history_messages.jsonl"
}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(workspace):
    # 生成workspace目录下的文件快照。
    workspace = Path(workspace).expanduser().resolve()
    manifest = {}
    for path in workspace.rglob("*"):
        relative_path = path.relative_to(workspace)
        relative_text = relative_path.as_posix()
        if ".git" in relative_path.parts or relative_path.parts[0] == ".agent_tool_outputs":
            continue
        if relative_text in INTERNAL_FILES:
            continue
        if path.is_symlink():
            manifest[relative_text] = {
                "type": "symlink",
                "target": os.readlink(path),
            }
        elif path.is_file():
            manifest[relative_text] = {
                "type": "file",
                "size": path.stat().st_size,
                "sha256": file_hash(path)
            }
    return manifest


def create_baseline(agent_workspace):
    agent_workspace = Path(agent_workspace).expanduser().resolve()
    baseline_path = agent_workspace.parent / "baseline.json"
    manifest = build_manifest(agent_workspace)
    baseline_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return baseline_path


def create_change_report(agent_workspace):
    agent_workspace = Path(agent_workspace).expanduser().resolve()
    baseline_path = agent_workspace.parent / "baseline.json"
    if not baseline_path.is_file():
        raise RuntimeError(f"缺少任务初始文件清单：{baseline_path}")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = build_manifest(agent_workspace)
    baseline_paths = set(baseline)
    current_paths = set(current)
    report = {
        "added": sorted(current_paths - baseline_paths),
        "deleted": sorted(baseline_paths - current_paths),
        "modified": sorted(
            path
            for path in baseline_paths & current_paths
            if baseline[path] != current[path]
        )
    }
    report_path = agent_workspace.parent / "changes.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report, report_path


def check_source_conflicts(source_workspace, agent_work_space, report):
    source_workspace = Path(source_workspace).expanduser().resolve()
    agent_work_space = Path(agent_work_space).expanduser().resolve()
    baseline_path = agent_work_space.parent / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    source_current = build_manifest(source_workspace)
    conflicts = []
    for path in report["added"]:
        if path in source_current:
            conflicts.append(path)
    for path in report["modified"] + report["deleted"]:
        if source_current.get(path) != baseline.get(path):
            conflicts.append(path)
    return sorted(set(conflicts))


def safe_target_path(source_workspace, relative_path):
    target = source_workspace / relative_path
    resolved_parent = target.parent.resolve()
    if not (
            resolved_parent == source_workspace
            or source_workspace in resolved_parent.parents
    ):
        raise RuntimeError(f"目标路径越过源目录：{relative_path}")
    return target


def apply_changes(source_workspace, agent_workspace):
    source_workspace = Path(source_workspace).expanduser().resolve()
    agent_workspace = Path(agent_workspace).expanduser().resolve()
    report, _ = create_change_report(agent_workspace)
    conflicts = check_source_conflicts(source_workspace, agent_workspace, report)
    if conflicts:
        raise RuntimeError(f"源目录存在冲突：{conflicts}")
    baseline_path = agent_workspace.parent / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    agent_current = build_manifest(agent_workspace)
    changed_paths = (report["added"] + report["modified"] + report["deleted"])
    for relative_path in changed_paths:
        before = baseline.get(relative_path)
        after = agent_current.get(relative_path)
        if (before is not None and before.get("type") == "symlink") or (
                after is not None and after.get("type") == "symlink"):
            raise RuntimeError(
                f"符号链接变化需要手动处理：{relative_path}"
            )
    # 检查路径
    for relative_path in report["added"] + report["modified"]:
        agent_file = agent_workspace / relative_path
        target_file = safe_target_path(source_workspace, relative_path)
        if not agent_file.is_file():
            raise RuntimeError(
                f"运行副本文件不存在：{relative_path}"
            )
        if target_file.exists() and target_file.is_dir():
            raise RuntimeError(
                f"目标是目录，不能覆盖：{relative_path}"
            )
    #
    for relative_path in report["deleted"]:
        target_file = safe_target_path(source_workspace, relative_path)
        if target_file.is_file():
            target_file.unlink()
        elif target_file.exists():
            raise RuntimeError(
                f"删除目标不是普通文件：{relative_path}"
            )
    #
    for relative_path in report["added"] + report["modified"]:
        agent_file = agent_workspace / relative_path
        target_file = safe_target_path(source_workspace, relative_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(agent_file, target_file)
    return report
