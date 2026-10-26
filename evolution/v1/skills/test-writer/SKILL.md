---
name: test-writer
description: 为 Python 函数或模块编写 pytest 测试。当用户要求补充测试或提高测试覆盖率时使用。
---

# Test Writer

使用 pytest 编写测试。

测试至少考虑：

- 正常输入。
- 边界输入。
- 非法输入。
- 异常处理。

优先测试对外行为，不依赖函数内部实现。

完成后运行：

```bash
pytest -q