from pathlib import Path
from string import Template


class PromptStore:
    def __init__(self, prompt_path):
        self.templates = {}
        for path in Path(prompt_path).glob("*.md"):
            text = path.read_text(encoding="utf-8-sig")
            if not text.strip():
                raise ValueError(f"提示词不能为空：{path}")
            self.templates[path.stem] = Template(text)

    def render(self, name, **values):
        if name not in self.templates:
            raise ValueError(f"提示词不存在：{name}.md")
        return self.templates[name].substitute(values)