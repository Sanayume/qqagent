"""
内置工具定义

提供 Agent 可以使用的基础工具。
"""

import ast
import contextvars
import operator
from datetime import datetime
from typing import Any, Callable
from langchain_core.tools import tool


# ==================== 实时消息回调 ====================

# 使用 ContextVar 实现线程/协程安全的回调隔离
# 每个 invoke_agent 调用设置自己的回调，不会互相覆盖
_send_message_callback_var: contextvars.ContextVar[Callable[[dict], None] | None] = \
    contextvars.ContextVar("send_message_callback", default=None)


def set_send_message_callback(callback: Callable[[dict], None] | None):
    """设置当前上下文的 send_message 回调函数

    使用 ContextVar 实现隔离，不同协程/会话的回调互不影响。

    Args:
        callback: 回调函数，接收消息指令 dict，立即处理发送
                  设为 None 则禁用实时发送
    """
    _send_message_callback_var.set(callback)


def get_send_message_callback() -> Callable[[dict], None] | None:
    """获取当前上下文的回调函数"""
    return _send_message_callback_var.get()


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
def send_message(
    text: str = "",
    image: str = "",
    at_users: Any = "",
    reply_to: int = 0,
) -> str:
    """发送消息到当前对话。这是你与用户交流的唯一方式。

    你的普通文字输出不会被任何人看到，只有调用此工具才能真正发送消息。
    你可以选择不调用（保持沉默），也可以调用一次或多次。

    【关键行为规则】
    1. 调用一次 send_message 就会发送一条消息，无需确认或重试
    2. 发送成功后，直接结束本轮对话，不要再调用任何工具
    3. 如果要发送多条消息，在一轮对话中连续调用多次，每次内容不同
    4. 绝对不要用相同或相似的内容重复调用此工具

    Args:
        text: 文本内容
        image: 图片 URL（可选）
        at_users: 要 @的用户 QQ 号，多个用逗号分隔，如 "123,456"（可选）
        reply_to: 要回复的消息 ID（可选）

    组合示例:
        - 纯文本: text="你好"
        - 纯图片: image="http://example.com/img.jpg"
        - 文本+图片: text="看这个", image="http://..."
        - @某人+文本: at_users="123456", text="你觉得呢"
        - 回复消息: reply_to=12345, text="同意"

    Returns:
        发送状态确认（看到确认后请结束对话，不要继续调用工具）
    """
    import json

    # 解析 at_users - 兼容多种输入格式
    at_list = []
    if at_users:
        # 如果是整数，直接添加
        if isinstance(at_users, int):
            at_list.append(at_users)
        # 如果是列表，遍历添加
        elif isinstance(at_users, list):
            for item in at_users:
                if isinstance(item, int):
                    at_list.append(item)
                elif isinstance(item, str) and item.strip().isdigit():
                    at_list.append(int(item.strip()))
        # 如果是字符串，按逗号分隔
        elif isinstance(at_users, str):
            for qq in at_users.split(","):
                qq = qq.strip()
                if qq.isdigit():
                    at_list.append(int(qq))

    # 构建发送指令
    command = {
        "_type": "send_message_command",
        "text": text,
        "image": image,
        "at_users": at_list,
        "reply_to": reply_to,
    }

    # 如果设置了实时回调，立即发送消息
    callback = get_send_message_callback()
    if callback is not None:
        try:
            callback(command)
        except Exception:
            # 回调失败不影响工具返回
            pass

    # 返回确认信息，明确告知消息已发送，LLM 应停止
    parts = []
    if text:
        parts.append(f"文本: {text[:50]}{'...' if len(text) > 50 else ''}")
    if image:
        parts.append(f"图片: {image[:30]}...")
    if at_list:
        parts.append(f"@: {at_list}")
    if reply_to:
        parts.append(f"回复: {reply_to}")

    # 返回消息明确告知 LLM 任务完成，应该停止
    return f"✓ 消息发送成功！({', '.join(parts) or '空消息'}) 【任务完成，请结束对话】"


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
    send_message,
    get_current_time,
    get_current_date,
    calculate,
]
