from pathlib import Path

from Agent.config.config import Config


def read(path, offset=1, limit=200):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"
    try:
        with open(p, "r", encoding="utf8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error{e}"
    total = len(lines)
    start = offset - 1
    if start >= total:
        return f"Error: offset {offset} exceeds file length ({total} lines)"
    end = min(start + limit, total)
    content = "".join(lines[start:end])
    if end < total:
        content += (
            f"\n\n[Showing lines {offset}-{end} of {total}. "
            f"Use offset={end + 1} to continue.]"
        )
    return content


READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read contents from a text file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Start line number, 1-based",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                    "minimum": 1,
                    "default": 200,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}
