import json

from openai import OpenAI

from Agent.config.config import Config


class ModelDeepSeek:
    def __init__(self):
        self.client = OpenAI(
            api_key=Config.api,
            base_url="https://api.deepseek.com")

    def generate_flash(self, messages, tools):
        response = self.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            tools=tools,
            timeout=300,
        )
        return response.choices[0].message, response.usage.total_tokens

    def generate_pro(self, messages, tools):
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            tools=tools,
            timeout=300,
        )
        return response.choices[0].message, response.usage.total_tokens

    def generate_usual(self, prompt, system_prompt):
        response = self.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            reasoning_effort="high",
            timeout=300,
            extra_body={"thinking": {"type": "enabled"}}
        )
        return response.choices[0].message.content, response.usage.total_tokens

    def generate_json(self, messages):
        response = self.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            response_format={
                'type': 'json_object'
            }
        )
        result = json.loads(response.choices[0].message.content)
        return result, response.usage.total_tokens
