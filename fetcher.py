"""
fetcher.py — 多源 AI 资讯抓取模块
覆盖：Papers With Code / Hugging Face / GitHub Trending / Hacker News AI / Reddit r/MachineLearning / OpenAI Blog / Anthropic Blog / Google DeepMind Blog
"""

import os
import re
import json
import time
import hashlib
import logging
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  RSS / API 信息源配置
# ─────────────────────────────────────────────
SOURCES = [
    # 顶级 AI 研究
    {
        "id": "arxiv_ai",
        "name": "arXiv · AI",
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "type": "rss",
        "category": "论文研究",
        "priority": 1,
    },
    {
        "id": "arxiv_cv",
        "name": "arXiv · 计算机视觉",
        "url": "https://rss.arxiv.org/rss/cs.CV",
        "type": "rss",
        "category": "论文研究",
        "priority": 2,
    },
    {
        "id": "arxiv_lg",
        "name": "arXiv · 机器学习",
        "url": "https://rss.arxiv.org/rss/cs.LG",
        "type": "rss",
        "category": "论文研究",
        "priority": 2,
    },
    # 大模型 / 产品动态
    {
        "id": "openai_blog",
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss",
        "category": "大模型动态",
        "priority": 1,
    },
    {
        "id": "anthropic_blog",
        "name": "Anthropic Blog",
        "url": "https://www.anthropic.com/rss.xml",
        "type": "rss",
        "category": "大模型动态",
        "priority": 1,
    },
    {
        "id": "deepmind_blog",
        "name": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "type": "rss",
        "category": "大模型动态",
        "priority": 1,
    },
    {
        "id": "mistral_blog",
        "name": "Mistral AI Blog",
        "url": "https://mistral.ai/rss",
        "type": "rss",
        "category": "大模型动态",
        "priority": 2,
    },
    # 开源 / 工具生态
    {
        "id": "huggingface_blog",
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "type": "rss",
        "category": "开源工具",
        "priority": 1,
    },
    {
        "id": "paperswithcode",
        "name": "Papers With Code",
        "url": "https://paperswithcode.com/rss.xml",
        "type": "rss",
        "category": "论文研究",
        "priority": 2,
    },
    # 社区 / 技术讨论
    {
        "id": "hackernews_ai",
        "name": "Hacker News · AI",
        "url": "https://hnrss.org/newest?q=AI+LLM+GPT+Claude+Gemini&points=50",
        "type": "rss",
        "category": "社区讨论",
        "priority": 2,
    },
    {
        "id": "the_batch",
        "name": "The Batch (Andrew Ng)",
        "url": "https://www.deeplearning.ai/the-batch/feed/",
        "type": "rss",
        "category": "行业观点",
        "priority": 1,
    },
    {
        "id": "import_ai",
        "name": "Import AI (Jack Clark)",
        "url": "https://jack-clark.net/feed/",
        "type": "rss",
        "category": "行业观点",
        "priority": 1,
    },
    # GitHub Trending 通过 API 抓取
    {
        "id": "github_trending",
        "name": "GitHub Trending · AI",
        "url": "https://api.github.com/search/repositories?q=topic:llm+topic:ai+created:>{}+stars:>50&sort=stars&order=desc&per_page=10",
        "type": "github_api",
        "category": "开源工具",
        "priority": 1,
    },
]

# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────
def _clean_html(raw: str) -> str:
    """剥离 HTML 标签，返回纯文本摘要（最多 400 字）"""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text[:400]


def _entry_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()[:12]


def _parse_date(entry) -> Optional[datetime]:
    """从 feedparser entry 解析发布时间"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _is_today_or_yesterday(dt: Optional[datetime], cutoff_hours: int = 72) -> bool:
    """只保留 cutoff_hours 小时内的内容（默认 72 小时，确保周末/节假日不漏）"""
    if dt is None:
        return True  # 无时间戳的内容默认保留
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() < cutoff_hours * 3600


# ─────────────────────────────────────────────
#  RSS 抓取
# ─────────────────────────────────────────────
def fetch_rss(source: dict, cutoff_hours: int = 72) -> list[dict]:
    items = []
    try:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries:
            pub_dt = _parse_date(entry)
            if not _is_today_or_yesterday(pub_dt, cutoff_hours):
                continue
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
            summary = _clean_html(summary_raw)
            if not title or not link:
                continue
            items.append({
                "id": _entry_id(link, title),
                "source_id": source["id"],
                "source_name": source["name"],
                "category": source["category"],
                "priority": source["priority"],
                "title": title,
                "url": link,
                "summary": summary,
                "published_at": pub_dt.isoformat() if pub_dt else None,
            })
    except Exception as e:
        logger.warning(f"RSS fetch failed [{source['id']}]: {e}")
    return items


# ─────────────────────────────────────────────
#  GitHub API 抓取
# ─────────────────────────────────────────────
def fetch_github_trending(source: dict) -> list[dict]:
    items = []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        url = source["url"].format(since)
        headers = {"Accept": "application/vnd.github.v3+json"}
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        repos = resp.json().get("items", [])
        for repo in repos[:10]:
            name = repo.get("full_name", "")
            description = repo.get("description", "") or ""
            stars = repo.get("stargazers_count", 0)
            html_url = repo.get("html_url", "")
            lang = repo.get("language", "")
            items.append({
                "id": _entry_id(html_url, name),
                "source_id": source["id"],
                "source_name": source["name"],
                "category": source["category"],
                "priority": source["priority"],
                "title": f"⭐ {stars:,}  {name}",
                "url": html_url,
                "summary": f"{description}  |  语言: {lang or '未知'}  |  Stars: {stars:,}",
                "published_at": None,
            })
    except Exception as e:
        logger.warning(f"GitHub API fetch failed: {e}")
    return items


# ─────────────────────────────────────────────
#  主入口
# ─────────────────────────────────────────────
def fetch_all(cutoff_hours: int = 72) -> list[dict]:
    """抓取所有源，返回去重后的新闻列表"""
    all_items = []
    seen_ids = set()

    for source in SOURCES:
        logger.info(f"Fetching [{source['id']}] ...")
        if source["type"] == "rss":
            items = fetch_rss(source, cutoff_hours)
        elif source["type"] == "github_api":
            items = fetch_github_trending(source)
        else:
            continue

        for item in items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_items.append(item)

        time.sleep(0.5)  # 礼貌性延迟，避免被封

    logger.info(f"Total fetched: {len(all_items)} items")
    return all_items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    items = fetch_all()
    print(json.dumps(items[:3], ensure_ascii=False, indent=2))
