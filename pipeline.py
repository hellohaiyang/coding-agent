import asyncio
import json
from uuid import uuid4

from pathlib import Path

from openai import APITimeoutError

from Agent.config.config import Config
from Agent.context.context_long_memory import LongMemory
from Agent.context.manager_context import ManagerContext
from Agent.environment.environment_workspace_changes import create_change_report, check_source_conflicts, apply_changes
from Agent.environment.environment_workspace_copy import create_work_space_copy
from Agent.environment.manager_environment import ManagerEnvironment
from Agent.model.manger_model import ManagerModel
from Agent.recovery.manager_recovery import ManagerRecovery
from Agent.recovery.recovery_state import AgentState, RunStatus, RunPhase, ToolCallState, ToolStatus
from Agent.utils import agent_print, valid_llm_response, dump_llm_response, ModelOutputFormatError


class Agent:
    def __init__(self, task=None, run_id=None, recovery=False, agent_workspace=None):
        self.agent_workspace = Path(agent_workspace)
        self.manager_model = ManagerModel(Config.model_name)
        self.manager_environment = ManagerEnvironment(run_id=run_id, agent_workspace=self.agent_workspace)
        self.manager_recovery = ManagerRecovery(agent_workspace=self.agent_workspace)
        self.long_memory = LongMemory(run_id)
        if recovery:
            # 恢复任务
            state = self.manager_recovery.load_state(run_id)
            if state is None:
                raise ValueError(f"任务不存在：{run_id}")
            self.agent_state = state
            self.manager_context = ManagerContext(state.task, agent_workspace=self.agent_workspace, run_id=run_id)
            context = self.manager_recovery.load_context(run_id)
            if context:
                self.manager_context.compression = context["compression"]
                self.manager_context.recent_messages = context["recent_messages"]
            else:
                self.manager_context.recent_messages = self.manager_recovery.load_messages(run_id)
        else:
            if not task:
                raise ValueError(f"新任务必须提供task")
            self.agent_state = AgentState(run_id=run_id, task=task)
            self.manager_context = ManagerContext(task, agent_workspace=self.agent_workspace, run_id=run_id)
            self.save_step()

    async def recovery(self):
        state = self.agent_state
        if state.status == RunStatus.SUCCEEDED:
            return state.final_answer
        if state.status in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.LIMIT_REACHED}:
            raise RuntimeError(f"当前任务状态不能自动恢复{state.status.value}")
        state.status = RunStatus.RUNNING
        self.save_step()
        if state.phase == RunPhase.READY_FOR_LLM:
            return await self.run()
        if state.phase == RunPhase.LLM_INFLIGHT:
            return await self.recover_llm()
        if state.phase in {RunPhase.TOOLS_PENDING, RunPhase.TOOLS_RUNNING}:
            recovered = await self.recover_tools()
            if not recovered:
                return None
            return await self.run()

    async def run(self):
        state = self.agent_state
        state.status = RunStatus.RUNNING
        self.save_step()
        try:
            while state.step < Config.max_step and state.used_tokens < Config.max_tokens:
                step_ans = await self.run_step()
                if step_ans["status"] == "success":
                    agent_print(f"token消耗{state.used_tokens}", mode=2)
                    return step_ans["content"]
                if step_ans["status"] == "blocked":
                    agent_print(step_ans["content"], mode=2)
                    return None
            state.status = RunStatus.LIMIT_REACHED
            if state.step >= Config.max_step:
                state.error = f"达到最大执行轮数：{Config.max_step}"
            elif state.used_tokens >= Config.max_tokens:
                state.error = f"达到最大 Token 数：{Config.max_tokens}"
            self.save_step()
            return None
        except asyncio.CancelledError:
            state.status = RunStatus.INTERRUPTED
            self.save_step()
            raise
        except APITimeoutError as e:
            state.status = RunStatus.INTERRUPTED
            state.phase = RunPhase.READY_FOR_LLM
            state.error = (
                f"LLM 请求超时，单次超时 "
            )
            self.save_step()
            agent_print(state.error, mode=2)
            return None
        except Exception as e:
            state.status = RunStatus.FAILED
            state.error = str(e)
            self.save_step()
            raise

    @staticmethod
    def get_tool_signature(tool_name, arguments_json):
        try:
            arguments = json.loads(arguments_json)
            normalized_arguments = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            normalized_arguments = str(arguments_json)
        return tool_name, normalized_arguments

    def get_used_tool_attempts(self, tool_state):
        target_signature = self.get_tool_signature(
            tool_state.tool_name,
            tool_state.arguments_json,
        )
        used_attempts = 0
        for existing_state in self.manager_recovery.load_recent_tool_calls(tool_state.run_id):
            existing_signature = self.get_tool_signature(existing_state.tool_name, existing_state.arguments_json)
            if existing_signature == target_signature:
                used_attempts += existing_state.attempt
        return used_attempts

    async def execute_tool_call(self, tool_state):
        used_attempts = self.get_used_tool_attempts(tool_state)
        if used_attempts >= Config.tool_max_attempts:
            error = (
                f"工具达到最大尝试次数："
                f"{used_attempts}/{Config.tool_max_attempts}"
            )
            result = {
                "success": False,
                "output": None,
                "error": error,
                "error_code": "tool_attempt_limit_reached",
            }
            tool_state.status = ToolStatus.FAILED
            tool_state.error = error
            tool_state.result_json = json.dumps(result, ensure_ascii=False)
            self.manager_recovery.save_tool_call(tool_state)
            return {
                "tool_call_id": tool_state.tool_call_id,
                "tool_name": tool_state.tool_name,
                "result": result,
                "success": False,
            }
        tool_state.status = ToolStatus.RUNNING
        tool_state.attempt += 1
        tool_state.error = None
        self.manager_recovery.save_tool_call(tool_state)
        try:
            function_name = tool_state.tool_name
            arguments = json.loads(tool_state.arguments_json)
            result = await  self.manager_environment.run_tool(function_name, arguments)
            # save
            tool_state.result_json = json.dumps(result, ensure_ascii=False, default=str)
            if result["success"]:
                tool_state.status = ToolStatus.SUCCEEDED
                tool_state.error = None
            else:
                tool_state.status = ToolStatus.FAILED
                tool_state.error = result["error"]
            self.manager_recovery.save_tool_call(tool_state)
            return {
                "tool_call_id": tool_state.tool_call_id,
                "tool_name": function_name,
                "result": result,
                "success": result["success"],
            }
        except Exception as e:
            tool_state.status = ToolStatus.FAILED
            tool_state.result_json = None
            tool_state.error = str(e)
            self.manager_recovery.save_tool_call(tool_state)
            return {
                "tool_call_id": tool_state.tool_call_id,
                "tool_name": tool_state.tool_name,
                "result": f"工具执行失败: {e}",
                "success": False,
            }

    async def generate_valid_llm_response(self, messages):
        state = self.agent_state
        retry_messages = list(messages)
        max_attempts = Config.max_model_format_retries + 1
        last_error = None
        for attempt_number in range(1, max_attempts + 1):
            llm_response, used_token = await asyncio.to_thread(self.manager_model.generate_flash_use_tool,
                                                               retry_messages)
            state.used_tokens += used_token or 0
            self.save_step()
            try:
                valid_llm_response(llm_response)
                return llm_response
            except ModelOutputFormatError as error:
                last_error = error
                agent_print(
                    (
                        f"模型输出格式错误 "
                        f"{attempt_number}/{max_attempts}："
                        f"{error.code}，{error}"
                    ),
                    mode=2,
                )
                if attempt_number >= max_attempts:
                    break
                raw_output = dump_llm_response(llm_response)
                repair_prompt = (
                    "上一条模型响应格式无效，请重新生成。\n"
                    f"错误类型：{error.code}\n"
                    f"错误详情：{error}\n"
                    "不要解释错误，也不要使用 Markdown 代码块。\n"
                    "如果需要调用工具，请生成符合工具 Schema 的工具调用。\n"
                    "如果不需要调用工具，请返回非空的最终答案。\n"
                    "上一条无效输出如下：\n"
                    f"{raw_output}"
                )
                retry_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": repair_prompt
                    }
                ]
        raise ModelOutputFormatError(
            "format_retry_exhausted",
            (
                f"模型连续 {max_attempts} 次返回无效格式；"
                f"最后错误：{last_error.code}，{last_error}"
            ),
        )

    async def run_step(self):
        agent_print(f"第{self.agent_state.step}轮次开始\n", 2)
        state = self.agent_state
        # 先压缩上下文
        compressed_token = await asyncio.to_thread(self.manager_context.run_compression)
        if compressed_token != -1:
            state.used_tokens += compressed_token
            self.manager_recovery.save_context(state.run_id, self.manager_context.compression,
                                               self.manager_context.recent_messages)
        messages = self.manager_context.build_context()
        state.phase = RunPhase.LLM_INFLIGHT
        self.save_step()
        try:
            llm_response = await self.generate_valid_llm_response(messages)
        except ModelOutputFormatError as error:
            state.status = RunStatus.INTERRUPTED
            state.phase = RunPhase.READY_FOR_LLM
            state.error = str(error)
            self.save_step()
            return {
                "status": "blocked",
                "content": state.error,
            }
        agent_print(
            f"LLM的回答\n{llm_response.content}\n",
            mode=2,
        )

        # llm_response, used_token = await asyncio.to_thread(self.manager_model.generate_flash_use_tool, messages)
        # state.used_tokens += used_token
        # self.save_step()
        # agent_print(f"LLM的回答\n{llm_response.content}\n", 2)
        # 保存消息
        assistant_message = self.manager_context.add_messages_assistant(llm_response)
        message_seq = self.manager_recovery.get_next_message_seq(state.run_id)
        self.manager_recovery.save_message(state.run_id, message_seq, assistant_message)
        self.manager_recovery.save_context(
            state.run_id,
            self.manager_context.compression,
            self.manager_context.recent_messages,
        )
        if llm_response.tool_calls:
            # 定义状态
            tool_states = {}
            for tool_call in llm_response.tool_calls:
                tool_state = ToolCallState(state.run_id, tool_call.id, tool_call.function.name,
                                           tool_call.function.arguments)
                self.manager_recovery.save_tool_call(tool_state)  # 逐个保存工具的状态
                tool_states[tool_call.id] = tool_state
            #
            state.phase = RunPhase.TOOLS_PENDING
            self.save_step()
            tasks = [
                self.execute_tool_call(tool_state)
                for tool_state in tool_states.values()
            ]
            state.phase = RunPhase.TOOLS_RUNNING
            self.save_step()
            results = await asyncio.gather(*tasks)
            for item in results:
                # 保存tool结果的消息
                tool_message = self.manager_context.add_messages_tool(
                    role="tool",
                    tool_call_id=item["tool_call_id"],
                    content=str(item["result"]),
                )
                message_tool_seq = self.manager_recovery.get_next_message_seq(state.run_id)
                self.manager_recovery.save_message(state.run_id, message_tool_seq, tool_message)
                self.manager_recovery.save_context(
                    state.run_id,
                    self.manager_context.compression,
                    self.manager_context.recent_messages,
                )
            # check fail
            if self.manager_recovery.has_consecutive_tool_failures(state.run_id, Config.max_consecutive_tool_failures):
                state.status = RunStatus.INTERRUPTED
                state.phase = RunPhase.READY_FOR_LLM
                state.error = (
                    f"工具连续失败 "
                    f"{Config.max_consecutive_tool_failures} 次，"
                    "已停止继续调用工具，需要人工处理"
                )
                self.save_step()
                return {
                    "status": "blocked",
                    "content": state.error,
                }
            state.step += 1
            state.phase = RunPhase.READY_FOR_LLM
            self.save_step()
            # 提取长期记忆
            if (state.step) % 8 == 0:
                try:
                    used_token = await asyncio.to_thread(self.long_memory.extract_long_memory,
                                                         self.manager_context.recent_messages)
                    state.used_tokens += used_token
                except Exception as e:
                    agent_print(f"长期记忆提取失败：{e}", mode=2)
                self.save_step()
            return {
                "status": "continue",
                "content": results,
            }
        else:
            state.step += 1
            state.final_answer = llm_response.content
            state.status = RunStatus.SUCCEEDED
            state.error = None
            self.save_step()
            used_token = await asyncio.to_thread(self.long_memory.extract_long_memory,
                                                 self.manager_context.recent_messages)
            state.used_tokens += used_token
            self.save_step()
            return {
                "status": "success",
                "content": llm_response.content,
            }

    def save_step(self):
        self.manager_recovery.save_state(self.agent_state)

    async def recover_tools(self):
        state = self.agent_state
        tool_states = {
            item.tool_call_id: item
            for item in self.manager_recovery.load_tool_calls(state.run_id)
        }
        # 获取最近一条对话的工具
        current_tool_call_ids = []
        for message in reversed(self.manager_context.recent_messages):
            if message.get("role") == "assistant" and message.get("tool_calls"):
                current_tool_call_ids = [
                    item["id"]
                    for item in message["tool_calls"]
                ]
                break
        if not current_tool_call_ids:
            state.status = RunStatus.INTERRUPTED
            state.error = "没找到当前轮次的工具调用"
            self.save_step()
            return False
        existing_tool_messages = {
            message.get("tool_call_id")
            for message in self.manager_context.recent_messages
            if message.get("role") == "tool"
        }
        state.phase = RunPhase.TOOLS_RUNNING
        state.error = None
        self.save_step()
        uncertain_tools = []
        for tool_call_id in current_tool_call_ids:
            tool_state = tool_states.get(tool_call_id)
            if tool_state is None:
                uncertain_tools.append(tool_call_id)
                continue
            if tool_call_id in existing_tool_messages:
                # 如果工具消息已经存在就说明执行完了，所以可以直接跳过
                continue
            result_item = None
            needs_confirmation = False
            if tool_state.status == ToolStatus.PENDING:
                result_item = await  self.execute_tool_call(tool_state)
            elif tool_state.status == ToolStatus.SUCCEEDED:
                if tool_state.result_json is None:
                    tool_state.status = ToolStatus.UNCERTAIN
                    self.manager_recovery.save_tool_call(tool_state)
                    needs_confirmation = True
                else:
                    result_item = {
                        "tool_call_id": tool_state.tool_call_id,
                        "result": json.loads(tool_state.result_json),
                    }
            elif tool_state.status == ToolStatus.FAILED:
                result_item = {
                    "tool_call_id": tool_state.tool_call_id,
                    "result": (f"工具执行失败{tool_state.error}")
                }
            elif tool_state.status == ToolStatus.RUNNING:
                if tool_state.tool_name == "read":
                    tool_state.status = ToolStatus.PENDING
                    self.manager_recovery.save_tool_call(tool_state)
                    result_item = await self.execute_tool_call(tool_state)
                else:
                    tool_state.status = ToolStatus.UNCERTAIN
                    self.manager_recovery.save_tool_call(tool_state)
                    needs_confirmation = True
            elif tool_state.status == ToolStatus.UNCERTAIN:
                needs_confirmation = True
            if needs_confirmation:
                answer = input(
                    f"工具结果不确定：\n"
                    f"工具：{tool_state.tool_name}\n"
                    f"参数：{tool_state.arguments_json}\n"
                    f"重新执行可能产生重复副作用，输入 yes 同意："
                ).strip().lower()
                if answer in {"yes", "y", "是"}:
                    tool_state.status = ToolStatus.PENDING
                    self.manager_recovery.save_tool_call(tool_state)
                    result_item = await self.execute_tool_call(tool_state)
                else:
                    uncertain_tools.append(tool_call_id)
                    continue
            if result_item is not None:
                # save
                message_seq = self.manager_recovery.get_next_message_seq(self.agent_state.run_id)
                message = self.manager_context.add_messages_tool("tool", result_item["tool_call_id"],
                                                                 str(result_item["result"]))
                self.manager_recovery.save_message(self.agent_state.run_id, message_seq, message)
                self.manager_recovery.save_context(
                    state.run_id,
                    self.manager_context.compression,
                    self.manager_context.recent_messages,
                )
        if uncertain_tools:
            state.status = RunStatus.INTERRUPTED
            state.error = (
                    "以下工具执行结果不确定，需要人工处理："
                    + ", ".join(uncertain_tools)
            )
            self.save_step()
            return False
        state.phase = RunPhase.READY_FOR_LLM
        state.step += 1
        state.error = None
        self.save_step()
        return True

    async def recover_llm(self):
        # 实际只有两种情况，API是否返回。API没返回结果重新请求。API返回结果是工具，就恢复工具。API返回结果是答案，直接复用答案。
        state = self.agent_state
        messages = self.manager_context.recent_messages
        last_message = messages[-1] if messages else None
        # 没保存模型的响应，直接重新调API
        if last_message is None or last_message.get("role") != "assistant":
            state.phase = RunPhase.READY_FOR_LLM
            state.error = None
            self.save_step()
            return await self.run()
        tool_calls = last_message.get("tool_calls") or []
        # 模型已经返回了工具，直接用模型返回的结果
        if tool_calls:
            existing_tool_states = {
                item.tool_call_id: item
                for item in self.manager_recovery.load_tool_calls(state.run_id)
            }
            for tool_call in tool_calls:
                tool_call_id = tool_call["id"]
                if tool_call_id in existing_tool_states:
                    continue
                function = tool_call["function"]
                tool_state = ToolCallState(run_id=state.run_id, tool_call_id=tool_call_id, tool_name=function["name"],
                                           arguments_json=function["arguments"])
                self.manager_recovery.save_tool_call(tool_state)
            state.phase = RunPhase.TOOLS_PENDING
            state.error = None
            self.save_step()
            recoverd = await self.recover_tools()
            if not recoverd:
                return None
            return await self.run()
        # 模型已经返回了最终的答案
        final_answer = last_message.get("content")
        if (
                not isinstance(final_answer, str)
                or not final_answer.strip()
        ):
            state.status = RunStatus.INTERRUPTED
            state.error = "模型响应没有内容，也没有工具调用"
            self.save_step()
            return None
        state.step += 1
        state.final_answer = final_answer
        state.status = RunStatus.SUCCEEDED
        state.error = None
        self.save_step()
        return final_answer


async def main():
    task = input("输入任务：")
    run_id = uuid4().hex
    # 复制目录
    agent_workspace = create_work_space_copy(Config.workspace, run_id)
    # 启动任务
    agent = Agent(task=task, run_id=run_id, agent_workspace=agent_workspace)
    try:
        await agent.run()
        await asyncio.to_thread(agent.manager_environment.sandbox.stop)
        report, report_path = create_change_report(agent_workspace)
        print(f"新增文件：{report['added']}")
        print(f"修改文件：{report['modified']}")
        print(f"删除文件：{report['deleted']}")
        print(f"变更报告：{report_path}")
        conflicts = check_source_conflicts(Config.workspace, agent_workspace, report)
        if conflicts:
            print(f"源目录存在冲突，不能自动应用：{conflicts}")
        elif not any(report.values()):
            print("没有需要应用的文件变化")
        elif agent.agent_state.status != RunStatus.SUCCEEDED:
            print(
                f"任务状态为 {agent.agent_state.status.value}，"
                "只保留变更报告，不允许应用"
            )
        else:
            answer = input("是否应用变更,apply：").strip()
            if answer == "apply":
                applied = apply_changes(Config.workspace, agent_workspace)
                print(
                    "变更已应用："
                    f"新增 {len(applied['added'])}，"
                    f"修改 {len(applied['modified'])}，"
                    f"删除 {len(applied['deleted'])}"
                )
            else:
                print("未应用变更，运行副本仍然保留")
    except asyncio.CancelledError:
        print("\n任务已中断")
        print(f"run_id: {agent.agent_state.run_id}")
        with Config.run_id_interrupt_path.open("a", encoding="utf-8") as file:
            file.write(agent.agent_state.run_id + "\n")
        raise
    finally:
        try:
            await asyncio.to_thread(
                agent.manager_environment.sandbox.remove
            )
        except Exception as error:
            # 清理失败不能覆盖任务原本的结果或异常
            agent_print(f"容器自动删除失败：{error}", mode=2)


async def recovery_main(run_id):
    agent_workspace = Config.run_workspace / run_id / "workspace"
    if not agent_workspace.is_dir():
        raise ValueError(
            f"任务副本不存在：{agent_workspace}"
        )
    agent = Agent(run_id=run_id, recovery=True, agent_workspace=agent_workspace)
    try:
        await agent.recovery()
        await asyncio.to_thread(agent.manager_environment.sandbox.stop)
        report, report_path = create_change_report(agent_workspace)
        print(f"新增文件：{report['added']}")
        print(f"修改文件：{report['modified']}")
        print(f"删除文件：{report['deleted']}")
        print(f"变更报告：{report_path}")
        conflicts = check_source_conflicts(Config.workspace, agent_workspace, report)
        if conflicts:
            print(f"源目录存在冲突，不能自动应用：{conflicts}")
        elif not any(report.values()):
            print("没有需要应用的文件变化")
        elif agent.agent_state.status != RunStatus.SUCCEEDED:
            print(
                f"任务状态为 {agent.agent_state.status.value}，"
                "只保留变更报告，不允许应用"
            )
        else:
            answer = input("是否应用变更,apply：").strip()
            if answer == "apply":
                applied = apply_changes(Config.workspace, agent_workspace)
                print(
                    "变更已应用："
                    f"新增 {len(applied['added'])}，"
                    f"修改 {len(applied['modified'])}，"
                    f"删除 {len(applied['deleted'])}"
                )
            else:
                print("未应用变更，运行副本仍然保留")

    finally:
        try:
            await asyncio.to_thread(
                agent.manager_environment.sandbox.remove
            )
        except Exception as error:
            # 清理失败不能覆盖任务原本的结果或异常
            agent_print(f"容器自动删除失败：{error}", mode=2)


if __name__ == "__main__":
    mode = input("新任务还是恢复(new/uuid)：")
    if mode == "new":
        asyncio.run(main())
    else:
        asyncio.run(recovery_main(mode))
