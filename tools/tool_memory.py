from copy import deepcopy

from Agent.tools.tool_read import READ_SCHEMA
from Agent.tools.tool_write import WRITE_SCHEMA
from Agent.tools.tool_edit import EDIT_SCHEMA


def make_memory_schema(source, name, description):
    schema = deepcopy(source)
    function = schema["function"]
    function["name"] = name
    function["description"] = description
    function["parameters"]["properties"]["path"]["description"] = (
        "memory 目录内的相对路径，只允许 User.md、Memory.md、"
        "Dreaming.md 或 daily_memory/YYYY-MM-DD.md，"
        "不要传绝对路径。"
    )
    return schema


MEMORY_SCHEMAS = [
    make_memory_schema(
        READ_SCHEMA,
        "readmemory",
        "分页读取历史记忆。offset 从 1 开始；"
        "返回 content、total_lines、next_offset。",
    ),
    make_memory_schema(
        WRITE_SCHEMA,
        "writememory",
        "追加值得长期保存的记忆，不覆盖原文。"
        "用户偏好写 User.md，长期事实写 Memory.md，"
        "当天事件写 daily_memory/YYYY-MM-DD.md。",
    ),
    make_memory_schema(
        EDIT_SCHEMA,
        "editmemory",
        "修正已有记忆。先 readmemory，"
        "提供唯一匹配的 old_text 和替换后的 new_text。",
    ),
]
SEARCH_MEMORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "使用向量检索和 BM25 混合检索历史记忆。"
            "返回来源路径、行号和片段；"
            "需要更多上下文时调用 readmemory。"
            "只搜索 memory 目录，不搜索项目代码或互联网。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "需要查找的事实、偏好、决策或历史问题"
                    ),
                    "minLength": 1,
                    "maxLength": 2000,
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回片段数",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}
MEMORY_SCHEMAS.append(SEARCH_MEMORY_SCHEMA)
