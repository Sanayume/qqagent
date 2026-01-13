"""
内置工具定义

提供 Agent 可以使用的基础工具。
"""

import ast
import operator
from datetime import datetime
from langchain_core.tools import tool


# ==================== 安全数学表达式求值 ====================

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "int": int,
    "float": float,
}


def _eval_node(node) -> float:
    """递归求值 AST 节点"""
    # 数字字面量
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value)}")

    # 二元运算: a + b, a * b, etc.
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return SAFE_OPERATORS[op_type](left, right)

    # 一元运算: -a, +a
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return SAFE_OPERATORS[op_type](operand)

    # 函数调用: abs(x), round(x, 2)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("只支持简单函数调用")
        func_name = node.func.id
        if func_name not in SAFE_FUNCTIONS:
            raise ValueError(f"不支持的函数: {func_name}")
        args = [_eval_node(arg) for arg in node.args]
        return SAFE_FUNCTIONS[func_name](*args)

    # 变量名 (仅用于函数名检查，实际变量不支持)
    if isinstance(node, ast.Name):
        raise ValueError(f"不支持的变量: {node.id}")

    raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


def safe_eval(expr: str) -> float:
    """安全的数学表达式求值

    支持: +, -, *, /, //, **, %, 括号, abs, round, min, max, pow
    """
    try:
        tree = ast.parse(expr, mode='eval')
        return _eval_node(tree.body)
    except SyntaxError as e:
        raise ValueError(f"表达式语法错误: {e}")


# ==================== 工具定义 ====================


@tool
def get_current_time() -> str:
    """获取当前时间。返回格式化的日期时间字符串。"""
    now = datetime.now()
    return now.strftime("%Y年%m月%d日 %H:%M:%S")


@tool  
def get_current_date() -> str:
    """获取今天的日期信息，包括星期几。"""
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    return f"{now.strftime('%Y年%m月%d日')} {weekday}"


@tool
def calculate(expression: str) -> str:
    """计算数学表达式。支持基本的四则运算、幂运算、取模等。

    Args:
        expression: 数学表达式，如 '2 + 3 * 4' 或 '2 ** 10'

    Returns:
        计算结果

    支持的运算:
        - 四则运算: +, -, *, /
        - 整除: //
        - 幂运算: ** 或 pow(x, y)
        - 取模: %
        - 函数: abs, round, min, max, int, float
    """
    try:
        result = safe_eval(expression)
        # 如果是整数结果，去掉小数点
        if isinstance(result, float) and result.is_integer():
            return str(int(result))
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"


# 默认工具列表
DEFAULT_TOOLS = [
    get_current_time,
    get_current_date,
    calculate,
]
