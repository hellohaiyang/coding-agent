import re
from datetime import date, datetime
from threading import RLock
from uuid import uuid4
import hashlib
import json
import sqlite3
import struct
from contextlib import closing
from pathlib import Path
from contextlib import closing, contextmanager
from Agent.config.config import Config
from Agent.model.manger_model import ManagerModel
from Agent.utils import agent_print


class LongMemory:
    def __init__(self, run_id, memory_root, prompts):
        self.run_id = run_id
        self.prompts = prompts
        self.manager_model = ManagerModel(prompts=self.prompts)
        self.root = Path(memory_root).expanduser().resolve()
        self._lock = RLock()
        self._embedding_model = None
        self._embedding_model_key = ""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "daily_memory").mkdir(exist_ok=True)
        for name in ("User.md", "Memory.md", "Dreaming.md"):
            target = self._memory_path(name)
            if not target.exists():
                self._write_memory_file(target, "")
        self.user_memory_path = self._memory_path("User.md")
        self.project_memory_path = self._memory_path("Memory.md")
        self._init_memory_tables()

    def _memory_path(self, name):
        name = name.replace("\\", "/")
        if name not in {"User.md", "Memory.md", "Dreaming.md"}:
            match = re.fullmatch(r"daily_memory/(\d{4}-\d{2}-\d{2})\.md", name)
            if match is None:
                raise ValueError(
                    "只允许访问指定的记忆 Markdown 文件"
                )
            date.fromisoformat(match.group(1))
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("记忆路径不能越过 memory 目录")
        return path

    @staticmethod
    def _read_memory_file(path):
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _write_memory_file(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{uuid4().hex}.tmp"
        )
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def readmemory(self, path, offset=1, limit=200):
        if offset < 1 or not 1 <= limit <= 2000:
            raise ValueError(
                "offset 必须 >= 1，limit 必须在 1 到 2000 之间"
            )
        with self._lock:
            target = self._memory_path(path)
            lines = self._read_memory_file(target).splitlines(
                keepends=True
            )
            begin = offset - 1
            end = min(begin + limit, len(lines))
            return {
                "path": target.relative_to(self.root).as_posix(),
                "content": "".join(lines[begin:end]),
                "total_lines": len(lines),
                "next_offset": (
                    end + 1 if end < len(lines) else None
                ),
            }

    def writememory(self, path, content):
        content = content.strip()
        if not content:
            raise ValueError("记忆内容不能为空")
        with self._lock:
            target = self._memory_path(path)
            previous = self._read_memory_file(target)
            if content in previous:
                return {
                    "path": path,
                    "appended": False,
                    "reason": "已存在",
                }
            updated = (
                previous.rstrip() + "\n\n" + content + "\n"
                if previous.strip()
                else content + "\n"
            )
            self._write_memory_file(target, updated)
            return {
                "path": path,
                "appended": True,
            }

    def editmemory(self, path, old_text, new_text):
        if not old_text:
            raise ValueError("old_text 不能为空")
        with self._lock:
            target = self._memory_path(path)
            previous = self._read_memory_file(target)
            count = previous.count(old_text)
            if count != 1:
                raise ValueError(
                    "old_text 必须唯一匹配，"
                    f"当前匹配 {count} 次，请先 readmemory"
                )
            self._write_memory_file(
                target,
                previous.replace(old_text, new_text, 1),
            )
            return {
                "path": path,
                "edited": True,
            }

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
        prompt = self.prompts.render(
            "memory_rewrite",
            instruction=instruction,
            previous_memory=previous_memory or "暂无",
            messages=str(messages),
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
                self.prompts.render("memory_user")
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
                self.prompts.render("memory_project")
            )
        except Exception as error:
            agent_print(
                f"项目长期记忆提取失败：{error}",
                mode=2,
            )
        return total_used_tokens

    def _get_embedding_model(self):
        from sentence_transformers import SentenceTransformer
        configured = Config.embedding_model_path.strip()
        if not configured:
            raise ValueError("请先配置 EMBEDDING_MODEL_PATH")
        model_path = Path(configured).expanduser().resolve()
        if not model_path.is_dir():
            raise ValueError(
                f"embedding 模型目录不存在：{model_path}"
            )
        key = str(model_path)
        if (
                self._embedding_model is None
                or self._embedding_model_key != key
        ):
            self._embedding_model = SentenceTransformer(
                key,
                local_files_only=True,
            )
            self._embedding_model_key = key
        return self._embedding_model

    def _memory_sources(self):
        names = ["User.md", "Memory.md", "Dreaming.md"]
        names.extend(
            f"daily_memory/{path.name}"
            for path in sorted(
                (self.root / "daily_memory").glob("*.md")
            )
        )
        sources = []
        for name in names:
            try:
                path = self._memory_path(name)
            except ValueError:
                continue
            if path.is_file():
                sources.append((
                    name,
                    path.read_text(encoding="utf-8"),
                ))
        return sources

    @staticmethod
    def _chunk_memory(sources, chunk_size=400, overlap=80):
        chunks = []
        for path, text in sources:
            begin = 0
            while begin < len(text):
                end = min(begin + chunk_size, len(text))
                content = text[begin:end]
                if content.strip():
                    chunks.append({
                        "path": path,
                        "start_line": (
                                text.count("\n", 0, begin) + 1
                        ),
                        "end_line": (
                                text.count("\n", 0, end - 1) + 1
                        ),
                        "content": content,
                    })
                if end == len(text):
                    break
                begin = end - overlap
        return chunks

    @staticmethod
    def _tokenize_memory(text):
        import jieba
        return [
            word.casefold()
            for word in jieba.lcut(text)
            if any(char.isalnum() for char in word)
        ]

    @staticmethod
    def _vector_bytes(vector):
        return struct.pack(f"{len(vector)}f", *vector)

    def _refresh_memory_index(
            self, db, sources, model, dimension
    ):
        snapshot = {
            "version": 1,
            "model": self._embedding_model_key,
            "dimension": dimension,
            "sources": sources,
        }
        signature = hashlib.sha256(
            json.dumps(
                snapshot,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory_index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        row = db.execute(
            "SELECT value FROM memory_index_meta WHERE key = ?",
            ("signature",),
        ).fetchone()
        if row is not None and row["value"] == signature:
            return
        chunks = self._chunk_memory(sources)
        vectors = (
            model.encode_document(
                [chunk["content"] for chunk in chunks],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            if chunks else []
        )
        # 只重建检索表；后续任务进度表不受影响。
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory_docs (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content)
        """)
        db.execute("DELETE FROM memory_fts")
        db.execute("DELETE FROM memory_docs")
        db.execute("DROP TABLE IF EXISTS memory_vec")
        db.execute(f"""
            CREATE VIRTUAL TABLE memory_vec
            USING vec0(embedding float[{dimension}])
        """)
        for doc_id, (chunk, vector) in enumerate(
                zip(chunks, vectors),
                1,
        ):
            db.execute("""
                INSERT INTO memory_docs
                    (id, path, start_line, end_line, content)
                VALUES (?, ?, ?, ?, ?)
            """, (
                doc_id,
                chunk["path"],
                chunk["start_line"],
                chunk["end_line"],
                chunk["content"],
            ))
            db.execute("""
                INSERT INTO memory_fts(rowid, content)
                VALUES (?, ?)
            """, (
                doc_id,
                " ".join(self._tokenize_memory(
                    chunk["path"] + "\n" + chunk["content"]
                )),
            ))
            db.execute("""
                INSERT INTO memory_vec(rowid, embedding)
                VALUES (?, ?)
            """, (
                doc_id,
                self._vector_bytes(vector),
            ))
        db.execute("""
            INSERT INTO memory_index_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (
            "signature",
            signature,
        ))

    def _bm25_memory_search(self, db, query, top_k):
        terms = list(dict.fromkeys(
            self._tokenize_memory(query)
        ))[:64]
        if not terms:
            return []
        expression = " OR ".join(
            '"' + term.replace('"', '""') + '"'
            for term in terms
        )
        rows = db.execute("""
            SELECT d.*, bm25(memory_fts) AS bm25_score
            FROM memory_fts
            JOIN memory_docs AS d
                ON d.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
            ORDER BY bm25_score, d.id
            LIMIT ?
        """, (
            expression,
            top_k,
        )).fetchall()
        return [dict(row) for row in rows]

    def _dense_memory_search(self, db, vector, top_k):
        rows = db.execute("""
            WITH matches AS (
                SELECT rowid, distance
                FROM memory_vec
                WHERE embedding MATCH ? AND k = ?
            )
            SELECT d.*, m.distance
            FROM matches AS m
            JOIN memory_docs AS d ON d.id = m.rowid
            ORDER BY m.distance, d.id
        """, (
            self._vector_bytes(vector),
            top_k,
        )).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _rrf_memory(dense, sparse, top_k):
        fused = {}
        for results in (dense, sparse):
            for rank, item in enumerate(results, 1):
                entry = fused.setdefault(
                    item["id"],
                    {**item, "rrf_score": 0.0},
                )
                entry["rrf_score"] += 1.0 / (60 + rank)
        return sorted(
            fused.values(),
            key=lambda item: item["rrf_score"],
            reverse=True,
        )[:top_k]

    def search(self, query, top_k=5):
        import sqlite_vec
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空")
        if not 1 <= top_k <= 10:
            raise ValueError("top_k 必须在 1 到 10 之间")
        with self._lock:
            sources = self._memory_sources()
            if not any(text.strip() for _, text in sources):
                return {
                    "query": query,
                    "results": [],
                }
            model = self._get_embedding_model()
            query_vector = model.encode_query(
                query,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            dimension = len(query_vector)
            with closing(sqlite3.connect(
                    self.root / "memory.db",
                    timeout=30,
            )) as db:
                db.row_factory = sqlite3.Row
                db.enable_load_extension(True)
                try:
                    sqlite_vec.load(db)
                finally:
                    db.enable_load_extension(False)
                with db:
                    self._refresh_memory_index(
                        db,
                        sources,
                        model,
                        dimension,
                    )
                candidates = top_k * 3
                sparse = self._bm25_memory_search(
                    db,
                    query,
                    candidates,
                )
                dense = self._dense_memory_search(
                    db,
                    query_vector,
                    candidates,
                )
                results = self._rrf_memory(
                    dense,
                    sparse,
                    top_k,
                )
            return {
                "query": query,
                "results": [
                    {
                        "path": item["path"],
                        "start_line": item["start_line"],
                        "end_line": item["end_line"],
                        "content": item["content"],
                        "rrf_score": round(
                            item["rrf_score"], 8
                        ),
                    }
                    for item in results
                ],
            }

    @contextmanager
    def _memory_state_db(self):
        with closing(sqlite3.connect(
                self.root / "memory.db", timeout=30
        )) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def _init_memory_tables(self):
        with self._memory_state_db() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS memory_turns (
                    run_id TEXT NOT NULL,
                    user_seq INTEGER NOT NULL,
                    end_seq INTEGER NOT NULL,
                    history_db TEXT NOT NULL,
                    project TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    extracted INTEGER NOT NULL DEFAULT 0,
                    dreamed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (run_id, user_seq)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS memory_jobs (
                    job_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0
                )
            """)

    def _record_completed_turn(self, history_db):
        history_db = Path(history_db).resolve()
        uri = history_db.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as source:
            source.row_factory = sqlite3.Row
            last = source.execute("""
                SELECT seq, message_json FROM agent_messages
                WHERE run_id = ?
                ORDER BY seq DESC LIMIT 1
            """, (self.run_id,)).fetchone()
            if last is None:
                return
            message = json.loads(last["message_json"])
            if (
                    message.get("role") != "assistant"
                    or message.get("tool_calls")
                    or not (message.get("content") or "").strip()
            ):
                return
            user_seq = source.execute("""
                SELECT MAX(seq) FROM agent_messages
                WHERE run_id = ?
                    AND role = 'user'
                    AND seq <= ?
            """, (
                self.run_id,
                last["seq"],
            )).fetchone()[0]
            if user_seq is None:
                return

        with self._memory_state_db() as db:
            db.execute("""
                INSERT OR IGNORE INTO memory_turns
                    (run_id, user_seq, end_seq, history_db,
                     project, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.run_id,
                user_seq,
                last["seq"],
                str(history_db),
                str(Path(Config.workspace).expanduser().resolve()),
                datetime.now().isoformat(timespec="seconds"),
            ))

    def _history_pages(self, turns):
        budget = Config.memory_extract_chars
        if budget < 4000:
            raise ValueError("memory_extract_chars 不能小于 4000")
        piece_size = budget // 2
        pages = [[]]
        current_size = 0
        for turn in turns:
            uri = Path(turn["history_db"]).as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as source:
                rows = source.execute("""
                    SELECT seq, message_json
                    FROM agent_messages
                    WHERE run_id = ? AND seq BETWEEN ? AND ?
                    ORDER BY seq
                """, (
                    turn["run_id"],
                    turn["user_seq"],
                    turn["end_seq"],
                )).fetchall()
            for seq, raw in rows:
                message = json.loads(raw)
                message.pop("reasoning_content", None)
                text = json.dumps(message, ensure_ascii=False)
                for begin in range(0, len(text), piece_size):
                    item = {
                        "source": f'{turn["run_id"]}:{seq}',
                        "project": turn["project"],
                        "date": turn["completed_at"][:10],
                        "role": message.get("role"),
                        "part": begin // piece_size + 1,
                        "message_fragment": (
                            text[begin:begin + piece_size]
                        ),
                    }
                    size = len(json.dumps(
                        item, ensure_ascii=False
                    ))
                    if pages[-1] and current_size + size > budget:
                        pages.append([])
                        current_size = 0
                    pages[-1].append(item)
                    current_size += size
        return [page for page in pages if page]

    def _memory_extract_prompt(self, page, allowed, dream):
        previous = {
            name: self._read_memory_file(
                self._memory_path(name)
            )[-Config.max_size_long_term_memory:]
            for name in sorted(allowed)
        }
        instruction = self.prompts.render(
            "memory_dream" if dream else "memory_extract"
        )
        return self.prompts.render(
            "memory_plan",
            instruction=instruction,
            previous=json.dumps(previous, ensure_ascii=False),
            page=json.dumps(page, ensure_ascii=False),
        )

    def _validate_memory_plan(self, plan, allowed):
        if (
                not isinstance(plan, dict)
                or set(plan) != {"writes", "edits"}
        ):
            raise ValueError(
                "提取结果必须包含 writes 和 edits 两个数组"
            )
        for key, fields in (
                ("writes", {"path", "content"}),
                ("edits", {"path", "old_text", "new_text"}),
        ):
            items = plan[key]
            if not isinstance(items, list) or len(items) > 20:
                raise ValueError("每类记忆操作最多 20 条")
            for item in items:
                if (
                        not isinstance(item, dict)
                        or set(item) != fields
                ):
                    raise ValueError("记忆操作字段错误")
                if not all(
                        isinstance(value, str)
                        for value in item.values()
                ):
                    raise ValueError(
                        "记忆操作参数必须是字符串"
                    )
                if any(
                        len(value) > 20000
                        for value in item.values()
                ):
                    raise ValueError("单条记忆操作内容过长")
                path = self._memory_path(item["path"])
                name = path.relative_to(self.root).as_posix()
                if name not in allowed:
                    raise ValueError(
                        f"本批次不允许修改：{name}"
                    )
                item["path"] = name
                if key == "writes" and not item["content"].strip():
                    raise ValueError("新增记忆不能为空")
                if key == "edits" and not item["old_text"]:
                    raise ValueError(
                        "修改记忆的 old_text 不能为空"
                    )

    def _apply_memory_plan(
            self, plan, job_id, check_only=False
    ):
        token = hashlib.sha256(
            job_id.encode("utf-8")
        ).hexdigest()[:16]
        operations = (
                [("write", item) for item in plan["writes"]]
                + [("edit", item) for item in plan["edits"]]
        )
        updates = {}
        for index, (kind, item) in enumerate(operations):
            path = self._memory_path(item["path"])
            if path not in updates:
                updates[path] = self._read_memory_file(path)
            previous = updates[path]
            marker = f"<!-- memory:{token}:{index} -->"
            if marker in previous:
                continue
            if kind == "write":
                content = item["content"].strip()
                updated = previous
                if content not in previous:
                    updated = (
                        previous.rstrip() + "\n\n" + content
                        if previous.strip()
                        else content
                    )
            else:
                count = previous.count(item["old_text"])
                if count != 1:
                    raise ValueError(
                        f'{item["path"]} 的 old_text '
                        f"匹配 {count} 次，无法安全修改记忆"
                    )
                updated = previous.replace(
                    item["old_text"],
                    item["new_text"],
                    1,
                )
            updates[path] = (
                    updated.rstrip() + "\n\n" + marker + "\n"
            )
        if not check_only:
            for path, content in updates.items():
                self._write_memory_file(path, content)

    def _process_pending_memory(self, dream=False):
        used_tokens = 0
        try:
            count = (
                1 if dream else Config.memory_extract_every
            )
            if count < 1:
                raise ValueError(
                    "memory_extract_every 必须 >= 1"
                )
            flag = "dreamed" if dream else "extracted"
            with self._memory_state_db() as db:
                turns = [
                    dict(row)
                    for row in db.execute(f"""
                        SELECT * FROM memory_turns
                        WHERE {flag} = 0
                        ORDER BY completed_at, run_id, user_seq
                        LIMIT ?
                    """, (count,)).fetchall()
                ]
            if len(turns) < count:
                return {
                    "used_tokens": 0,
                    "error": None,
                }
            allowed = (
                {"Dreaming.md"}
                if dream else
                {"User.md", "Memory.md"}
            )
            if not dream:
                allowed.update(
                    f'daily_memory/{turn["completed_at"][:10]}.md'
                    for turn in turns
                )
            identity = [
                "v1",
                flag,
                [
                    (
                        turn["run_id"],
                        turn["user_seq"],
                        turn["end_seq"],
                    )
                    for turn in turns
                ],
            ]
            batch_id = hashlib.sha256(
                json.dumps(identity).encode("utf-8")
            ).hexdigest()
            pages = self._history_pages(turns)
            if not pages:
                raise ValueError(
                    "历史消息为空，无法提取记忆"
                )
            for index, page in enumerate(pages):
                job_id = f"{batch_id}:{index}"
                with self._memory_state_db() as db:
                    job = db.execute(
                        "SELECT * FROM memory_jobs WHERE job_id = ?",
                        (job_id,),
                    ).fetchone()
                if job is not None and job["done"]:
                    continue
                if job is None:
                    raw, tokens = (
                        self.manager_model.generate_usual_flash(
                            self._memory_extract_prompt(
                                page, allowed, dream
                            )
                        )
                    )
                    used_tokens += tokens or 0
                    plan = json.loads(raw)
                    self._validate_memory_plan(plan, allowed)
                    self._apply_memory_plan(
                        plan, job_id, check_only=True
                    )
                    with self._memory_state_db() as db:
                        db.execute("""
                            INSERT INTO memory_jobs
                                (job_id, batch_id, plan_json)
                            VALUES (?, ?, ?)
                        """, (
                            job_id,
                            batch_id,
                            json.dumps(
                                plan, ensure_ascii=False
                            ),
                        ))
                else:
                    plan = json.loads(job["plan_json"])
                    self._validate_memory_plan(
                        plan, allowed
                    )
                self._apply_memory_plan(plan, job_id)
                with self._memory_state_db() as db:
                    db.execute(
                        "UPDATE memory_jobs "
                        "SET done = 1 WHERE job_id = ?",
                        (job_id,),
                    )
                if dream:
                    break

            with self._memory_state_db() as db:
                finished = db.execute("""
                    SELECT COUNT(*) FROM memory_jobs
                    WHERE batch_id = ? AND done = 1
                """, (batch_id,)).fetchone()[0]
                if finished == len(pages):
                    for turn in turns:
                        db.execute(f"""
                            UPDATE memory_turns
                            SET {flag} = 1
                            WHERE run_id = ? AND user_seq = ?
                        """, (
                            turn["run_id"],
                            turn["user_seq"],
                        ))
            return {
                "used_tokens": used_tokens,
                "error": None,
            }

        except Exception as error:
            return {
                "used_tokens": used_tokens,
                "error": str(error),
            }

    def on_turn_completed(self, history_db):
        with self._lock:
            self._record_completed_turn(history_db)
            return self._process_pending_memory()

    def dream_pending(self):
        with self._lock:
            return self._process_pending_memory(dream=True)
