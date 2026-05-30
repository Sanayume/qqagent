"""
简单网页正文提取器

测试爬取给定的比如 cnBeta 文章链接，提取出标题和正文纯文本。
可以后续集成到 Agent 知识库入库清洗流中。
"""

import sys
import requests
from bs4 import BeautifulSoup

def extract_article(url: str):
    print(f"🔗 正在抓取: {url}")
    try:
        # 伪装成人，防止遇到初级 403
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        # cnBeta 等大部分中文新闻网站编码为 utf-8，保险起见让 requests 推断
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 1. 尝试找标题
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)

        # cnBeta 常见的标题和内容容器特征
        article_title = soup.find('h1', class_='title')
        if article_title:
            title = article_title.get_text(strip=True)

        # 2. 尝试找正文内容区
        content_div = soup.find('div', class_='article-content') or soup.find('div', class_='content')

        text_content = ""
        if content_div:
            # 删去一些无用的内嵌 script / style
            for tag in content_div(['script', 'style']):
                tag.decompose()
            text_content = content_div.get_text(separator='\n', strip=True)
        else:
            # Fallback 策略：如果找不到特定 class，就把 body 里的所有 p 标签文字集合起来
            paragraphs = soup.find_all('p')
            text_content = "\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])

        print("✅ 抓取成功！\n")
        print("="*60)
        print(f"标题: {title}")
        print("="*60)
        # 截取前 500 字展示
        print(f"正文预览 (前500字):\n{text_content[:500]} ...\n\n共 {len(text_content)} 字")
        print("="*60)

    except Exception as e:
        print(f"❌ 抓取失败: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        target_url = "https://www.cnbeta.com.tw/articles/soft/1551054.htm"
    extract_article(target_url)
