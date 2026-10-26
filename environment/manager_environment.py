from Agent.config.config import Config
# from Agent.environment.environment_auto_check_tool import AutoCheckTools
from Agent.environment.environment_docker_sandbox import DockerSandbox
from Agent.tools.manager_tool import ManagerTools
from Agent.utils import agent_print


class ManagerEnvironment:
    def __init__(self, run_id, agent_workspace,system_prompt,skill_path):
        self.agent_workspace = agent_workspace
        self.sandbox = DockerSandbox(run_id=run_id, agent_workspace=agent_workspace)
        self.manager_tool = ManagerTools(
            agent_workspace=self.agent_workspace,
            sandbox=self.sandbox,
            system_prompt=system_prompt,
            skill_path=skill_path,
        )

    async def run_tool(self, tool_name, arguments):
        return await self.manager_tool.run_tool(tool_name, arguments)
