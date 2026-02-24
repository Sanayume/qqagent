"""
文本渲染模块

将 Markdown 文本渲染成二次元风格的图片。
技术栈：Markdown → HTML → Playwright 截图 → PNG
"""

import random
import time
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension


# ==================== 数据结构 ====================

@dataclass
class RenderResult:
    """渲染结果"""
    success: bool
    image_path: str = ""
    error: str = ""
    width: int = 0
    height: int = 0

    def to_tool_response(self) -> str:
        """转换为工具返回格式"""
        if self.success:
            return f"渲染成功！\n图片路径: {self.image_path}\n尺寸: {self.width}x{self.height}"
        return f"渲染失败: {self.error}"


# ==================== 常量 ====================

MAX_TEXT_LENGTH = 50000
MAX_IMAGE_HEIGHT = 10000
OUTPUT_DIR = Path("workspace/renders")

# 二次元风格 CSS
KAWAII_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: "Times New Roman", "Noto Serif SC", "SimSun", serif;
    font-size: 16px;
    line-height: 1.8;
    background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
    padding: 30px;
    min-height: 100vh;
}

.content {
    background: rgba(255, 255, 255, 0.95);
    border-radius: 20px;
    border: 3px solid #ffb6c1;
    box-shadow: 0 8px 32px rgba(255, 182, 193, 0.3);
    padding: 30px;
    max-width: 100%;
    overflow-wrap: break-word;
    word-wrap: break-word;
}

/* 标题样式 */
h1, h2, h3, h4, h5, h6 {
    color: #d63384;
    margin: 1em 0 0.5em 0;
    font-weight: 700;
}

h1 {
    font-size: 1.8em;
    border-bottom: 2px solid #ffb6c1;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.5em;
    border-bottom: 1px solid #ffb6c1;
    padding-bottom: 0.2em;
}

h3 { font-size: 1.3em; }
h4 { font-size: 1.1em; }

/* 段落 */
p {
    margin: 0.8em 0;
    color: #333;
}

/* 链接 */
a {
    color: #ff69b4;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* 列表 */
ul, ol {
    margin: 0.8em 0;
    padding-left: 2em;
}

li {
    margin: 0.3em 0;
}

/* 引用块 */
blockquote {
    margin: 1em 0;
    padding: 10px 20px;
    background: linear-gradient(135deg, #fff0f5 0%, #ffe4e9 100%);
    border-left: 4px solid #ff69b4;
    border-radius: 0 12px 12px 0;
    color: #666;
    font-style: italic;
}

/* 代码块 */
pre {
    background: #2d2d2d;
    border-radius: 12px;
    border-left: 4px solid #ff69b4;
    padding: 15px;
    margin: 1em 0;
    overflow-x: auto;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 14px;
    line-height: 1.5;
}

pre code {
    background: none;
    padding: 0;
    color: #f8f8f2;
}

/* 行内代码 */
code {
    background: #fff0f5;
    color: #d63384;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 0.9em;
}

/* 表格 */
table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 1em 0;
    border: 2px solid #ffb6c1;
    border-radius: 12px;
    overflow: hidden;
}

th {
    background: linear-gradient(135deg, #ffb6c1 0%, #ff69b4 100%);
    color: white;
    font-weight: 700;
    padding: 12px 15px;
    text-align: left;
}

td {
    padding: 10px 15px;
    border-top: 1px solid #ffb6c1;
}

tr:nth-child(even) {
    background: #fff5f8;
}

tr:hover {
    background: #ffe4e9;
}

/* 水平线 */
hr {
    border: none;
    height: 2px;
    background: linear-gradient(90deg, transparent, #ffb6c1, transparent);
    margin: 1.5em 0;
}

/* 图片 */
img {
    max-width: 100%;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

/* 代码高亮 - Monokai 风格 */
.codehilite .hll { background-color: #49483e }
.codehilite .c { color: #75715e } /* Comment */
.codehilite .err { color: #960050; background-color: #1e0010 } /* Error */
.codehilite .k { color: #66d9ef } /* Keyword */
.codehilite .l { color: #ae81ff } /* Literal */
.codehilite .n { color: #f8f8f2 } /* Name */
.codehilite .o { color: #f92672 } /* Operator */
.codehilite .p { color: #f8f8f2 } /* Punctuation */
.codehilite .ch { color: #75715e } /* Comment.Hashbang */
.codehilite .cm { color: #75715e } /* Comment.Multiline */
.codehilite .cp { color: #75715e } /* Comment.Preproc */
.codehilite .cpf { color: #75715e } /* Comment.PreprocFile */
.codehilite .c1 { color: #75715e } /* Comment.Single */
.codehilite .cs { color: #75715e } /* Comment.Special */
.codehilite .gd { color: #f92672 } /* Generic.Deleted */
.codehilite .ge { font-style: italic } /* Generic.Emph */
.codehilite .gi { color: #a6e22e } /* Generic.Inserted */
.codehilite .gs { font-weight: bold } /* Generic.Strong */
.codehilite .gu { color: #75715e } /* Generic.Subheading */
.codehilite .kc { color: #66d9ef } /* Keyword.Constant */
.codehilite .kd { color: #66d9ef } /* Keyword.Declaration */
.codehilite .kn { color: #f92672 } /* Keyword.Namespace */
.codehilite .kp { color: #66d9ef } /* Keyword.Pseudo */
.codehilite .kr { color: #66d9ef } /* Keyword.Reserved */
.codehilite .kt { color: #66d9ef } /* Keyword.Type */
.codehilite .ld { color: #e6db74 } /* Literal.Date */
.codehilite .m { color: #ae81ff } /* Literal.Number */
.codehilite .s { color: #e6db74 } /* Literal.String */
.codehilite .na { color: #a6e22e } /* Name.Attribute */
.codehilite .nb { color: #f8f8f2 } /* Name.Builtin */
.codehilite .nc { color: #a6e22e } /* Name.Class */
.codehilite .no { color: #66d9ef } /* Name.Constant */
.codehilite .nd { color: #a6e22e } /* Name.Decorator */
.codehilite .ni { color: #f8f8f2 } /* Name.Entity */
.codehilite .ne { color: #a6e22e } /* Name.Exception */
.codehilite .nf { color: #a6e22e } /* Name.Function */
.codehilite .nl { color: #f8f8f2 } /* Name.Label */
.codehilite .nn { color: #f8f8f2 } /* Name.Namespace */
.codehilite .nx { color: #a6e22e } /* Name.Other */
.codehilite .py { color: #f8f8f2 } /* Name.Property */
.codehilite .nt { color: #f92672 } /* Name.Tag */
.codehilite .nv { color: #f8f8f2 } /* Name.Variable */
.codehilite .ow { color: #f92672 } /* Operator.Word */
.codehilite .w { color: #f8f8f2 } /* Text.Whitespace */
.codehilite .mb { color: #ae81ff } /* Literal.Number.Bin */
.codehilite .mf { color: #ae81ff } /* Literal.Number.Float */
.codehilite .mh { color: #ae81ff } /* Literal.Number.Hex */
.codehilite .mi { color: #ae81ff } /* Literal.Number.Integer */
.codehilite .mo { color: #ae81ff } /* Literal.Number.Oct */
.codehilite .sa { color: #e6db74 } /* Literal.String.Affix */
.codehilite .sb { color: #e6db74 } /* Literal.String.Backtick */
.codehilite .sc { color: #e6db74 } /* Literal.String.Char */
.codehilite .dl { color: #e6db74 } /* Literal.String.Delimiter */
.codehilite .sd { color: #e6db74 } /* Literal.String.Doc */
.codehilite .s2 { color: #e6db74 } /* Literal.String.Double */
.codehilite .se { color: #ae81ff } /* Literal.String.Escape */
.codehilite .sh { color: #e6db74 } /* Literal.String.Heredoc */
.codehilite .si { color: #e6db74 } /* Literal.String.Interpol */
.codehilite .sx { color: #e6db74 } /* Literal.String.Other */
.codehilite .sr { color: #e6db74 } /* Literal.String.Regex */
.codehilite .s1 { color: #e6db74 } /* Literal.String.Single */
.codehilite .ss { color: #e6db74 } /* Literal.String.Symbol */
.codehilite .bp { color: #f8f8f2 } /* Name.Builtin.Pseudo */
.codehilite .fm { color: #a6e22e } /* Name.Function.Magic */
.codehilite .vc { color: #f8f8f2 } /* Name.Variable.Class */
.codehilite .vg { color: #f8f8f2 } /* Name.Variable.Global */
.codehilite .vi { color: #f8f8f2 } /* Name.Variable.Instance */
.codehilite .vm { color: #f8f8f2 } /* Name.Variable.Magic */
.codehilite .il { color: #ae81ff } /* Literal.Number.Integer.Long */
"""


# ==================== 核心函数 ====================

def _markdown_to_html(text: str) -> str:
    """将 Markdown 转换为 HTML"""
    md = markdown.Markdown(
        extensions=[
            'tables',
            'fenced_code',
            CodeHiliteExtension(
                linenums=False,
                css_class='codehilite',
                guess_lang=True,
            ),
            'nl2br',
        ]
    )
    return md.convert(text)


def _wrap_html(content_html: str, width: int) -> str:
    """包装 HTML，添加完整的页面结构和样式"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, initial-scale=1.0">
    <style>
{KAWAII_CSS}
    </style>
</head>
<body>
    <div class="content">
{content_html}
    </div>
</body>
</html>"""


def _screenshot(html: str, output_path: Path, width: int) -> tuple[int, int]:
    """使用 Playwright 截图"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.set_content(html, wait_until="networkidle")

        # 获取实际内容高度
        height = page.evaluate("document.body.scrollHeight")
        height = min(height, MAX_IMAGE_HEIGHT)

        # 截图
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()

    return width, height


def render_text(
    text: str,
    width: int = 800,
    theme: str = "kawaii",
) -> RenderResult:
    """将 Markdown 文本渲染成图片

    Args:
        text: Markdown 文本
        width: 图片宽度（默认 800）
        theme: 主题（目前仅支持 kawaii）

    Returns:
        RenderResult 包含渲染结果
    """
    # 验证输入
    if not text or not text.strip():
        return RenderResult(success=False, error="文本内容不能为空")

    if len(text) > MAX_TEXT_LENGTH:
        return RenderResult(
            success=False,
            error=f"文本过长 ({len(text)} > {MAX_TEXT_LENGTH} 字符)"
        )

    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    filename = f"render_{int(time.time())}_{random.randint(1000, 9999)}.png"
    output_path = OUTPUT_DIR / filename

    try:
        # Markdown → HTML
        content_html = _markdown_to_html(text)

        # 包装完整 HTML
        full_html = _wrap_html(content_html, width)

        # 截图
        actual_width, actual_height = _screenshot(full_html, output_path, width)

        return RenderResult(
            success=True,
            image_path=str(output_path.absolute()).replace(chr(92), '/'),
            width=actual_width,
            height=actual_height,
        )

    except ImportError as e:
        if "playwright" in str(e).lower():
            return RenderResult(
                success=False,
                error="Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        return RenderResult(success=False, error=f"缺少依赖: {e}")

    except Exception as e:
        return RenderResult(success=False, error=f"渲染失败: {e}")
