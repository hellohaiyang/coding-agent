def register(mcp):
    @mcp.tool()
    def add_numbers(a: int, b: int) -> dict:
        """计算两个整数之和。"""
        return {"sum": a + b}