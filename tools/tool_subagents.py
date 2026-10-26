from datetime import datetime
from crewai import Agent, Task, Crew, LLM, Process
from crewai.tools import tool
from concurrent.futures import ThreadPoolExecutor
from Agent.config.config import Config


def run_subagent(role: str, task: str, context: str = "", *, tools: list) -> dict:
    llm = LLM(
        model=f"openai/{Config.model_name}",
        api_key=Config.api,
        base_url="https://api.deepseek.com",
        temperature=0.2,
        timeout=60,
    )
    worker = Agent(
        role=role,
        goal="完成主 Agent 分配的任务，返回具体、准确的结果。",
        backstory=(
            "你是接受主 Agent 委派的专业助手。"
            "根据任务和提供的背景独立工作，使用中文回答。"
        ),
        llm=llm,
        tools=tools,
        cache=False,
        allow_delegation=False,
        max_iter=8,
        max_execution_time=120,
        verbose=False
    )
    assignment = Task(
        description=(
            f"请完成以下任务：\n{task}\n\n"
            f"相关背景资料：\n{context or '无'}"
        ),
        expected_output="直接给出任务成果，尽可能简洁。",
        agent=worker,
    )
    crew = Crew(
        agents=[worker],
        tasks=[assignment],
        verbose=False
    )
    result = crew.kickoff()
    return {
        "text": result.raw,
        "used_tokens": result.token_usage.total_tokens,
    }


def run_parallel_agents(
        tasks: list[dict],
        context: str = "",
        *, tools: list
) -> dict:
    def execute(item):
        llm = LLM(
            model=f"openai/{Config.model_name}",
            api_key=Config.api,
            base_url="https://api.deepseek.com",
            temperature=0.2,
            timeout=60,
        )
        worker = Agent(
            role=item["role"],
            goal="独立完成分配的任务，返回具体、准确的结果。",
            backstory="你是一名专业助手，根据任务和背景独立工作，使用中文回答。",
            llm=llm,
            tools=tools,
            cache=False,
            allow_delegation=False,
            max_iter=8,
            verbose=False,
        )
        assignment = Task(
            description=(
                f"任务：\n{item['task']}\n\n"
                f"背景资料：\n{context or '无'}"
            ),
            expected_output="直接给出具体任务成果。",
            agent=worker,
        )
        crew = Crew(
            agents=[worker],
            tasks=[assignment],
            verbose=False,
        )
        result = crew.kickoff()
        return {
            "text": f"【{item['role']}】\n{result.raw}",
            "used_tokens": result.token_usage.total_tokens,
        }
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(execute, tasks))
    return {
        "text": "\n\n".join(item["text"] for item in results),
        "used_tokens": sum(item["used_tokens"] for item in results),
    }


def run_agent_team(
        goal: str,
        members: list[dict],
        context: str = "",
        *, tools: list
) -> dict:
    agents = []
    assignments = []
    for member in members:
        llm = LLM(
            model=f"openai/{Config.model_name}",
            api_key=Config.api,
            base_url="https://api.deepseek.com",
            temperature=0.2,
            timeout=60,
        )
        worker = Agent(
            role=member["role"],
            goal=f"与其他成员协作完成共同目标：{goal}",
            backstory=(
                "你是团队中的专业成员，使用中文回答。"
                "需要其他成员的信息时，使用同事提问工具。"
                "需要其他成员帮忙完成工作时，使用委派工具。"
                "收到同事的提问或委派时，提供具体结果。"
            ),
            llm=llm,
            tools=tools,
            cache=False,
            allow_delegation=True,
            max_iter=8,
            verbose=False,
        )
        assignment = Task(
            description=(
                f"团队目标：\n{goal}\n\n"
                f"你的任务：\n{member['task']}\n\n"
                f"背景资料：\n{context or '无'}"
            ),
            expected_output="给出你负责部分的具体成果。",
            agent=worker
        )
        agents.append(worker)
        assignments.append(assignment)
    crew = Crew(
        agents=agents,
        tasks=assignments,
        process=Process.sequential,
        verbose=False,
    )
    result = crew.kickoff()
    return {
        "text": "\n\n".join(
            f"【{agent.role}】\n{assignment.output.raw}"
            for agent, assignment in zip(agents, assignments)
        ),
        "used_tokens": result.token_usage.total_tokens,
    }


SUBAGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_subagent",
        "description": "委派一个专业子 Agent 完成独立任务，并返回结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "子 Agent 的角色，例如代码审查员",
                    "minLength": 1,
                },
                "task": {
                    "type": "string",
                    "description": "明确、具体的任务要求",
                    "minLength": 1,
                },
                "context": {
                    "type": "string",
                    "description": "相关背景、本次用户要求和只读或修改限制",
                    "default": "",
                },
            },
            "required": ["role", "task"],
            "additionalProperties": False,
        },
    },
}

PARALLEL_AGENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_parallel_agents",
        "description": (
            "并行执行多个互相独立的任务，并汇总结果。"
            "不要安排修改同一文件或存在先后依赖的任务。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "需要并行执行的任务列表",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "description": "负责该任务的 Agent 角色",
                                "minLength": 1,
                            },
                            "task": {
                                "type": "string",
                                "description": "该 Agent 需要完成的独立任务",
                                "minLength": 1,
                            },
                        },
                        "required": ["role", "task"],
                        "additionalProperties": False,
                    },
                },
                "context": {
                    "type": "string",
                    "description": "各任务共享的背景、本次用户要求和操作限制",
                    "default": "",
                },
            },
            "required": ["tasks"],
            "additionalProperties": False,
        },
    },
}

AGENT_TEAM_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_agent_team",
        "description": (
            "组织多个专业成员协作完成共同目标。"
            "任务按成员顺序执行，成员可以相互提问和委派。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "整个团队需要完成的共同目标",
                    "minLength": 1,
                },
                "members": {
                    "type": "array",
                    "description": "团队成员及各自任务，按执行顺序排列",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "description": "成员的角色，团队内应保持唯一",
                                "minLength": 1,
                            },
                            "task": {
                                "type": "string",
                                "description": "该成员负责完成的任务",
                                "minLength": 1,
                            },
                        },
                        "required": ["role", "task"],
                        "additionalProperties": False,
                    },
                },
                "context": {
                    "type": "string",
                    "description": "团队共享的背景、本次用户要求和操作限制",
                    "default": "",
                },
            },
            "required": ["goal", "members"],
            "additionalProperties": False,
        },
    },
}
