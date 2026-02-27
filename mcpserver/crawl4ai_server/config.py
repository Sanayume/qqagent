"""
Crawl4AI MCP Server 配置
全部从环境变量加载，与 qqagent 其他 MCP 服务器风格一致。
"""
import os


class Config:
    # ── 浏览器配置 ──────────────────────────────────────────────
    headless: bool = os.getenv("CRAWL4AI_HEADLESS", "true").lower() == "true"
    # 代理（可选），格式：http://user:pass@host:port
    proxy: str = os.getenv("CRAWL4AI_PROXY", "")

    # ── 限速 / 并发 ──────────────────────────────────────────────
    # 爬取超时（秒）
    page_timeout: int = int(os.getenv("CRAWL4AI_PAGE_TIMEOUT", "30"))
    # 批量爬取最大并发数
    max_concurrent: int = int(os.getenv("CRAWL4AI_MAX_CONCURRENT", "5"))
    # 深度爬取最大页面数上限（防止意外爬取过多）
    deep_max_pages: int = int(os.getenv("CRAWL4AI_DEEP_MAX_PAGES", "20"))

    # ── 内容过滤 ─────────────────────────────────────────────────
    # PruningContentFilter 阈值（0~1），越高保留内容越少
    prune_threshold: float = float(os.getenv("CRAWL4AI_PRUNE_THRESHOLD", "0.48"))
    # 最小词数（过滤极短文本块）
    min_word_threshold: int = int(os.getenv("CRAWL4AI_MIN_WORD_THRESHOLD", "10"))

    # ── 截图输出 ─────────────────────────────────────────────────
    screenshot_dir: str = os.getenv("CRAWL4AI_SCREENSHOT_DIR", "workspace/screenshots")

    # ── 缓存 ──────────────────────────────────────────────────────
    # enabled / bypass / disabled
    cache_mode: str = os.getenv("CRAWL4AI_CACHE_MODE", "bypass")

    # ── 反爬 / Stealth ────────────────────────────────────────────
    stealth_mode: bool = os.getenv("CRAWL4AI_STEALTH", "true").lower() == "true"


config = Config()
