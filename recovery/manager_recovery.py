import json
from pathlib import Path

from Agent.config.config import Config
from Agent.recovery.recovery_state import AgentState, RunPhase, RunStatus, ToolCallState, ToolStatus
from Agent.sqlite.manager_sqlite import ManagerSQLite


class ManagerRecovery:
    def __init__(self, agent_workspace):
        db_path = Path(agent_workspace).parent / "agent_state.db"
        self.history_path = Path(agent_workspace) / "history_messages.jsonl"
        self.db = ManagerSQLite(str(db_path))
        self.create_table()

    def create_table(self):
        self.db.execute_sql_write("""
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        run_id TEXT PRIMARY KEY,
                        task TEXT NOT NULL,
                        status TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        step INTEGER NOT NULL,
                        used_tokens INTEGER NOT NULL,
                        final_answer TEXT,
                        error TEXT
                    )
                """)
        self.db.execute_sql_write("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                message_json TEXT NOT NULL,
                PRIMARY KEY (run_id, seq)
            )
        """)
        self.db.execute_sql_write("""
            CREATE TABLE IF NOT EXISTS agent_tool_calls (
                run_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                attempt INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (run_id, tool_call_id)
            )
        """)
        self.db.execute_sql_write("""
            CREATE TABLE IF NOT EXISTS agent_context (
                run_id TEXT PRIMARY KEY,
                context_json TEXT NOT NULL
            )
        """)

    def save_state(self, state: AgentState):
        self.db.execute_sql_write(
            """
            INSERT INTO agent_runs (
                run_id,
                task,
                status,
                phase,
                step,
                used_tokens,
                final_answer,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                task = excluded.task,
                status = excluded.status,
                phase = excluded.phase,
                step = excluded.step,
                used_tokens = excluded.used_tokens,
                final_answer = excluded.final_answer,
                error = excluded.error
            """,
            (
                state.run_id,
                state.task,
                state.status.value,
                state.phase.value,
                state.step,
                state.used_tokens,
                state.final_answer,
                state.error,
            ),
        )

    def load_state(self, run_id):
        rows = self.db.execute_sql_read(
            """
            SELECT
                run_id,
                task,
                status,
                phase,
                step,
                used_tokens,
                final_answer,
                error
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return AgentState(
            run_id=row[0],
            task=row[1],
            status=RunStatus(row[2]),
            phase=RunPhase(row[3]),
            step=row[4],
            used_tokens=row[5],
            final_answer=row[6],
            error=row[7],
        )

    def append_history_message(self, run_id, seq, message):
        # 讲历史消息保存到json文件，方便grep查找。
        record = {
            "run_id": run_id,
            "seq": seq,
            "message": message,
        }
        with self.history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_message(self, run_id, seq, message):
        message_json = json.dumps(message, ensure_ascii=False)
        self.db.execute_sql_write(
            """
            INSERT INTO agent_messages (
                run_id,
                seq,
                role,
                message_json
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, seq) DO UPDATE SET
                role = excluded.role,
                message_json = excluded.message_json
            """,
            (
                run_id,
                seq,
                message["role"],
                message_json,
            ),
        )
        self.append_history_message(run_id, seq, message)

    def load_messages(self, run_id):
        rows = self.db.execute_sql_read(
            """
            SELECT message_json
            FROM agent_messages
            WHERE run_id = ?
            ORDER BY seq ASC
            """,
            (run_id,),
        )
        return [
            json.loads(row[0])
            for row in rows
        ]

    def save_tool_call(self, tool_state):
        self.db.execute_sql_write(
            """
            INSERT INTO agent_tool_calls (
                run_id,
                tool_call_id,
                tool_name,
                arguments_json,
                status,
                result_json,
                error,
                attempt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, tool_call_id) DO UPDATE SET
                tool_name = excluded.tool_name,
                arguments_json = excluded.arguments_json,
                status = excluded.status,
                result_json = excluded.result_json,
                error = excluded.error,
                attempt = excluded.attempt
            """,
            (
                tool_state.run_id,
                tool_state.tool_call_id,
                tool_state.tool_name,
                tool_state.arguments_json,
                tool_state.status.value,
                tool_state.result_json,
                tool_state.error,
                tool_state.attempt,
            ),
        )

    def has_consecutive_tool_failures(self,run_id,limit=5):
        rows = self.db.execute_sql_read(
            """
            SELECT status
            FROM agent_tool_calls
            WHERE run_id = ?
              AND attempt > 0
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (run_id, limit),
        )
        if len(rows)<limit:
            return False
        return all(
            row[0]==ToolStatus.FAILED.value
            for row in rows
        )

    def load_recent_tool_calls(self, run_id, limit=5):
        rows = self.db.execute_sql_read(
            """
            SELECT
                run_id,
                tool_call_id,
                tool_name,
                arguments_json,
                status,
                result_json,
                error,
                attempt
            FROM agent_tool_calls
            WHERE run_id = ?
                AND attempt > 0
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (run_id, limit),
        )

        return [
            ToolCallState(
                run_id=row[0],
                tool_call_id=row[1],
                tool_name=row[2],
                arguments_json=row[3],
                status=ToolStatus(row[4]),
                result_json=row[5],
                error=row[6],
                attempt=row[7],
            )
            for row in rows
        ]

    def load_tool_calls(self, run_id):
        rows = self.db.execute_sql_read(
            """
            SELECT
                run_id,
                tool_call_id,
                tool_name,
                arguments_json,
                status,
                result_json,
                error,
                attempt
            FROM agent_tool_calls
            WHERE run_id = ?
            """,
            (run_id,),
        )

        return [
            ToolCallState(
                run_id=row[0],
                tool_call_id=row[1],
                tool_name=row[2],
                arguments_json=row[3],
                status=ToolStatus(row[4]),
                result_json=row[5],
                error=row[6],
                attempt=row[7],
            )
            for row in rows
        ]

    def get_next_message_seq(self, run_id):
        rows = self.db.execute_sql_read(
            """
            SELECT COALESCE(MAX(seq), -1) + 1
            FROM agent_messages
            WHERE run_id = ?
            """,
            (run_id,),
        )
        return rows[0][0]

    def save_context(self, run_id, compression, recent_messages):
        # 保存压缩的摘要和精简后的最近对话
        context_json = json.dumps(
            {
                "compression": compression,
                "recent_messages": recent_messages,
            },
            ensure_ascii=False,
        )
        self.db.execute_sql_write(
            """
            INSERT INTO agent_context (run_id, context_json)
            VALUES (?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                context_json = excluded.context_json
            """,
            (run_id, context_json),
        )

    def load_context(self, run_id):
        rows = self.db.execute_sql_read(
            """
            SELECT context_json
            FROM agent_context
            WHERE run_id = ?
            """,
            (run_id,),
        )
        if not rows:
            return None
        return json.loads(rows[0][0])
