from pathlib import Path


def edit(path, old_text, new_text):
    p = Path(path).expanduser().resolve()
    try:
        content = p.read_text(
            encoding="utf-8",
            errors="replace",
        )
        count = content.count(old_text)
        if count == 0:
            return "Error: old_text not found in file"

        if count > 1:
            return (
                f"Error: old_text appears {count} times. "
                "Please provide more surrounding text to make it unique."
            )
        content = content.replace(old_text, new_text, 1)
        p.write_text(content, encoding="utf-8")
        return f"Successfully edited {path}"
    except Exception as e:
        return f"Error: {e}"


EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": "Edit a file by replacing an exact piece of text.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find in the file",
                },
                "new_text": {
                    "type": "string",
                    "description": "Text to replace it with",
                },
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    },
}
