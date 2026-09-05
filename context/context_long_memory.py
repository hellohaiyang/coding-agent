from datetime import datetime

from pathlib import Path

from Agent.config.config import Config
from Agent.model.manger_model import ManagerModel
from Agent.utils import agent_print


class LongMemory:
    def __init__(self, run_id):
        self.manager_model = ManagerModel()
        self.user_memory_path = Config.user_long_term_memory
        self.project_memory_path = Config.get_project_long_term_memory_path(run_id)

    # def extract_long_memory(self, messages,memory_path):
    #     # 获取
    #     prompt = """
    #     将下面的内容提取成长期记忆，逐条输出。重点是用户的偏好，习惯，用户画像，背景信息等。字数尽可能简洁。\n
    #     """
    #     prompt += str(messages)
    #     # 拼接之前的长期记忆
    #     if memory_path.exists() and memory_path.is_file():
    #         pre_long_term_memory = memory_path.read_text(encoding="utf-8")
    #         prompt += "\n以下是之前的长期记忆，根据此次的内容，保留或更新。\n"
    #         if len(pre_long_term_memory) > Config.max_size_long_term_memory:
    #             prompt += pre_long_term_memory[:Config.max_size_long_term_memory]
    #             prompt += f"长期记忆过长，截断到{Config.max_size_long_term_memory}字"
    #         else:
    #             prompt += pre_long_term_memory
    #     long_term_memory, used_token = self.manager_model.generate_usual_flash(prompt)
    #     # 写入
    #     path = memory_path
    #     with open(path, "w", encoding="utf-8") as f:
    #         time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         f.write(f"[{time}] {long_term_memory}\n")
    #         f.write(f"\n\n")
    #     return used_token
    def extract_one_memory(
        self,
        messages,
        memory_path,
        instruction,
    ):
        memory_path = Path(memory_path)

        previous_memory = ""
        if memory_path.is_file():
            previous_memory = memory_path.read_text(
                encoding="utf-8"
            )

            if (
                len(previous_memory)
                > Config.max_size_long_term_memory
            ):
                previous_memory = previous_memory[
                    -Config.max_size_long_term_memory:
                ]

        prompt = (
            f"{instruction}\n\n"
            "请输出更新后的完整长期记忆，"
            "删除重复和过时内容，不要编造。\n\n"
            "之前的长期记忆：\n"
            f"{previous_memory or '暂无'}\n\n"
            "本次任务消息：\n"
            f"{messages}"
        )

        memory, used_token = (
            self.manager_model.generate_usual_flash(prompt)
        )

        if not isinstance(memory, str) or not memory.strip():
            raise ValueError("长期记忆提取结果为空")

        memory_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        memory_path.write_text(
            f"[更新时间：{time}]\n{memory.strip()}\n",
            encoding="utf-8",
        )

        return used_token

    def extract_long_memory(self, messages):
        total_used_tokens = 0

        try:
            total_used_tokens += self.extract_one_memory(
                messages,
                self.user_memory_path,
                (
                    "提取可以跨任务复用的用户长期信息："
                    "用户偏好、习惯、技术水平、沟通方式、"
                    "长期约束和开发环境。"
                    "不要记录项目实现细节。"
                ),
            )
        except Exception as error:
            agent_print(
                f"用户长期记忆提取失败：{error}",
                mode=2,
            )

        try:
            total_used_tokens += self.extract_one_memory(
                messages,
                self.project_memory_path,
                (
                    "提取当前 run_id 对应的项目长期信息："
                    "项目结构、技术栈、代码约定、常用命令、"
                    "设计决策、已知问题和长期待办。"
                    "不要记录用户画像。"
                ),
            )
        except Exception as error:
            agent_print(
                f"项目长期记忆提取失败：{error}",
                mode=2,
            )

        return total_used_tokens