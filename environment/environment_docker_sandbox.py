import os
import subprocess
from pathlib import Path

from Agent.config.config import Config
from Agent.utils import agent_print


class DockerSandbox:
    def __init__(self, run_id, agent_workspace):
        self.run_id = run_id
        self.container_name = f"codeagent-{self.run_id}"
        self.agent_workspace = Path(agent_workspace).expanduser().resolve()

    def run_docker(self, arguments, timeout=30, check=False):
        process = subprocess.run(
            ["docker", *arguments],
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        agent_print(
            f"\ndocker结果"
            f"\nreturncode: {process.returncode}"
            f"\nstdout:\n{process.stdout}"
            f"\nstderr:\n{process.stderr}\n",
            2,
        )
        if check and process.returncode != 0:
            raise RuntimeError(process.stderr or process.stdout or "docker fail")
        return process

    def container_exists(self):
        process = self.run_docker(
            [
                "container",
                "inspect",
                "--format",
                "{{.Id}}",
                self.container_name,
            ],
            timeout=10,
        )
        return process.returncode == 0

    def container_running(self):
        process = self.run_docker(
            [
                "container",
                "inspect",
                "--format",
                "{{.State.Running}}",
                self.container_name,
            ],
            timeout=10
        )
        return process.returncode == 0 and process.stdout.strip() == "true"

    def ensure_started(self):
        if self.container_exists():
            if not self.container_running():
                self.run_docker(
                    [
                        "container",
                        "start",
                        self.container_name,
                    ],
                    timeout=20,
                    check=True,
                )
            return
        command = [
            "container",
            "create",
            "--name",
            self.container_name,
            "--label",
            "codeagent.managed=true",
            "--label",
            f"codeagent.run_id={self.run_id}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            Config.sandbox_memory,
            "--memory-swap",
            Config.sandbox_memory,
            "--cpus",
            Config.sandbox_cpus,
            "--pids-limit",
            Config.sandbox_pids_limit,
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--env",
            "HOME=/tmp",
        ]
        if hasattr(os, "getuid"):
            command.extend(
                [
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                ]
            )
            command.extend(
                [
                    "--mount",
                    f"type=bind,src={self.agent_workspace},dst=/workspace",
                    Config.sandbox_image,
                    "sleep",
                    "infinity"
                ]
            )
        self.run_docker(
            command,
            timeout=30,
            check=True,
        )
        self.run_docker(
            [
                "container",
                "start",
                self.container_name,
            ],
            timeout=20,
            check=True,
        )

    def exec(self, command, timeout=30):
        self.ensure_started()
        try:
            process = self.run_docker(
                [
                    "container",
                    "exec",
                    self.container_name,
                    "/usr/bin/timeout",
                    "--signal=TERM",
                    "--kill-after=5s",
                    f"{timeout}s",
                    "/bin/bash",
                    "-lc",
                    command,
                ],
                timeout=timeout + 10,
            )
            return {
                "stdout": process.stdout[:Config.tool_max_output],
                "stderr": process.stderr[:Config.tool_max_output],
                "exit_code": process.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": (
                    f"timeout after {timeout} seconds"
                ),
                "exit_code": -1,
            }

    def stop(self):
        if not self.container_exists():
            return
        self.run_docker(
            [
                "container",
                "stop",
                "--time",
                "3",
                self.container_name,
            ],
            timeout=10,
        )

    def remove(self):
        if not self.container_exists():
            return
        self.run_docker(
            [
                "container",
                "rm",
                "--force",
                self.container_name,
            ],
            timeout=15,
        )
