import argparse
import importlib.util
import sys
from contextlib import redirect_stdout
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def load_tools(mcp, tools_dir):
    root = Path(tools_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"工具目录不存在：{root}")
    # 支持工具导入同目录的辅助模块。
    sys.path.insert(0, str(root))
    for path in sorted(root.glob("*.py")):
        # 下划线开头的文件作为辅助模块，不自动注册。
        if path.name.startswith("_"):
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"工具文件不能超出工具目录：{path}")
        module_name = f"evolution_tool_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载工具模块：{path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        with redirect_stdout(sys.stderr):
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise ValueError(f"工具模块缺少 register(mcp)：{path}")
            register(mcp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools-dir", required=True)
    args = parser.parse_args()

    mcp = FastMCP("EvolutionTools")
    load_tools(mcp, args.tools_dir)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()