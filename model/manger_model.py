from Agent.config.config import Config
from Agent.model.model_deepseek import ModelDeepSeek
from Agent.tools.manager_tool import TOOLS_SCHEMA

models = {
    "deepseek": ModelDeepSeek(),
}


class ManagerModel:
    def __init__(self, model_name="deepseek"):
        self.model = models[model_name]

    def generate_flash_use_tool(self, messages, tools=TOOLS_SCHEMA):
        return self.model.generate_flash(messages, tools)

    def generate_pre_use_tool(self, messages, tools=TOOLS_SCHEMA):
        return self.model.generate_pro(messages, tools)

    def generate_usual_flash(self, prompt):
        return self.model.generate_usual(prompt)

    def judge_task_complex(self, task):
        system_prompt = """
        用户会给定一个任务，你判断任务的复杂程度，是否需要制定计划执行。输出JSON格式。 
        answer字段只能是easy或hard。
        
        EXAMPLE INPUT: 
        帮我写一个计算器小程序

        EXAMPLE JSON OUTPUT:
        {
            "question": "帮我写一个计算器小程序",
            "answer": "easy"
        }
        
        EXAMPLE INPUT: 
        帮我制定旅游规划

        EXAMPLE JSON OUTPUT:
        {
            "question": "帮我制定旅游规划",
            "answer": "hard"
        }
        """
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": task}]
        return self.model.generate_json(messages)

