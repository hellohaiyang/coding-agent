from pathlib import Path


def write(path, content):
    p = Path(path).expanduser().resolve()
    if p.exists() and p.is_dir():
        return f"Error: path is a directory: {path}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"error {e}"


WRITE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write",
        "description": "Write content to a file. Creates parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
}
