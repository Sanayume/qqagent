"""路径修复工具"""

import re
from pathlib import Path

_ESCAPE_MAP = {'\t': 't', '\r': 'r', '\n': 'n'}


def fix_escaped_path(path: str) -> str:
    """修复被 JSON 转义损坏的路径（\\t \\r \\n 等）

    LLM 传参时反斜杠常被转义，导致路径中出现实际的制表符/换行符。
    如果原始路径不存在但修复后存在，返回修复后的路径。
    """
    if Path(path).exists():
        return path
    fixed = re.sub(r'[\t\r\n]', lambda m: '\\' + _ESCAPE_MAP[m.group()], path)
    if Path(fixed).exists():
        return fixed
    return path
