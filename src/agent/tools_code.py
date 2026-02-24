"""代码沙箱执行工具"""

import subprocess
import tempfile
from pathlib import Path
from langchain_core.tools import tool

LANG_CONFIG = {
    "python": {"ext": ".py", "cmd": ["python", "-u"]},
    "javascript": {"ext": ".js", "cmd": ["node"]},
    "js": {"ext": ".js", "cmd": ["node"]},
}


@tool
def run_code(code: str, language: str = "python", timeout: int = 30) -> str:
    """在沙箱中执行代码并返回输出。

    Args:
        code: 要执行的代码
        language: 编程语言（python/javascript）
        timeout: 超时秒数（最大60）

    Returns:
        代码执行的输出结果
    """
    language = language.lower()
    cfg = LANG_CONFIG.get(language)
    if not cfg:
        return f"不支持的语言: {language}，支持: {', '.join(LANG_CONFIG)}"

    timeout = max(1, min(60, timeout))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=cfg["ext"], delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp = Path(f.name)

    try:
        result = subprocess.run(
            cfg["cmd"] + [str(tmp)],
            capture_output=True, text=True, timeout=timeout,
            cwd=tempfile.gettempdir(),
        )
        output = result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if not output.strip():
            output = "(无输出)"
        # 截断过长输出
        if len(output) > 4000:
            output = output[:4000] + "\n...(输出已截断)"
        return output
    except subprocess.TimeoutExpired:
        return f"执行超时（{timeout}秒）"
    except Exception as e:
        return f"执行失败: {e}"
    finally:
        tmp.unlink(missing_ok=True)
