from Agent.config.config import Config
from Agent.model.model_deepseek import ModelDeepSeek
from Agent.tools.manager_tool import TOOLS_SCHEMA

models = {
    "deepseek": ModelDeepSeek(),
}


class ManagerModel:
    def __init__(self, model_name="deepseek",*,prompts):
        self.model = models[model_name]
        self.prompts = prompts

    def generate_flash_use_tool(self, messages, tools=TOOLS_SCHEMA):
        return self.model.generate_flash(messages, tools)

    def generate_pre_use_tool(self, messages, tools=TOOLS_SCHEMA):
        return self.model.generate_pro(messages, tools)

    def generate_usual_flash(self, prompt):
        return self.model.generate_usual(
            prompt,
            system_prompt=self.prompts.render("auxiliary_system"),
        )

    def judge_task_complex(self, task):
        system_prompt = self.prompts.render("task_complexity")
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": task}]
        return self.model.generate_json(messages)

