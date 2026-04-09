#!/usr/bin/env python3
"""
AI 每日日报生成脚本
从多平台抓取公开内容，再用 DeepSeek API 做筛选、总结和排版。
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
SKILL_PATH = BASE_DIR / "skills" / "ai-daily" / "SKILL.md"
CONFIG_PATH = BASE_DIR / "config" / "sources.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 25
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEFAULT_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
JINA_PREFIX = "https://r.jina.ai/http://"

AI_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "llm",
    "agent",
    "agents",
    "model",
    "models",
    "reasoning",
    "openai",
    "anthropic",
    "deepmind",
    "meta ai",
    "hugging face",
    "transformer",
    "multimodal",
    "benchmark",
    "inference",
    "deepseek",
    "qwen",
    "claude",
    "gemini",
]

LOW_VALUE_PATTERNS = [
    "self-promotion",
    "who's hiring",
    "who wants to be hired",
    "monthly who",
    "weekly who",
    "hiring thread",
    "job thread",
    "open thread",
]

FOCUS_PROMPTS = {
    "ecommerce": "优先保留 AI 电商、AI 导购、商业变现、零售自动化、营销提效相关内容。",
    "research": "优先保留模型架构、推理能力、benchmark、论文与底层能力突破。",
    "tools": "优先保留开发工具、API 更新、IDE 插件、Agent 工具链和使用方法。",
    "": "优先保留底层能力、商业落地、应用案例、使用方法、未来趋势和重要发布。",
}


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_low_value(text: str) -> bool:
    haystack = (text or "").lower()
    return any(pattern in haystack for pattern in LOW_VALUE_PATTERNS)


def as_jina_url(url: str) -> str:
    clean = url.replace("https://", "").replace("http://", "")
    return f"{JINA_PREFIX}{clean}"


def http_get(url: str) -> requests.Response:
    return requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=REQUEST_TIMEOUT,
    )


def request_text_with_fallback(urls: List[str]) -> Tuple[str, str]:
    last_error = None
    for url in urls:
        try:
            resp = http_get(url)
            resp.raise_for_status()
            return resp.text, url
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("没有可用请求地址")


def build_request_candidates(url: str, allow_jina: bool = True) -> List[str]:
    urls = [url]
    if allow_jina and "r.jina.ai" not in url:
        urls.append(as_jina_url(url))
    return urls


def looks_like_article(url: str, base_domain: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return False
    if base_domain not in parsed.netloc:
        return False
    path = parsed.path.lower()
    if any(x in path for x in ["/tag/", "/tags/", "/topic/", "/topics/", "/author/", "/search", "/videos"]):
        return False
    return len(path.strip("/").split("/")) >= 1


def parse_markdown_title_and_summary(text: str) -> Tuple[str, str]:
    lines = [line.strip() for line in text.splitlines()]
    title = ""
    for line in lines:
        if line.startswith("Title:"):
            title = clean_text(line.replace("Title:", "", 1))
            break
    if not title:
        for line in lines:
            if line.startswith("# "):
                title = clean_text(line[2:])
                break
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Markdown Content:"):
            body_start = i + 1
            break
    body_lines = []
    for line in lines[body_start:]:
        if not line or line.startswith("![") or line.startswith("[!"):
            continue
        if line.startswith("[") and "](" in line and len(line) < 25:
            continue
        body_lines.append(line)
        if len(" ".join(body_lines)) > 600:
            break
    summary = clean_text(" ".join(body_lines))[:600]
    return title[:220], summary


def extract_article_snapshot(url: str, source_name: str, platform: str) -> Dict[str, str]:
    try:
        text, used_url = request_text_with_fallback(build_request_candidates(url, allow_jina=True))
    except Exception:
        return {}

    if used_url.startswith(JINA_PREFIX):
        title, summary = parse_markdown_title_and_summary(text)
        published = ""
        m = re.search(r"Published Time:\s*(.+)", text)
        if m:
            published = clean_text(m.group(1))[:80]
        if not title:
            return {}
        return {
            "title": title,
            "summary": summary[:500],
            "url": url,
            "source": source_name,
            "platform": platform,
            "published_at": published,
        }

    soup = BeautifulSoup(text, "html.parser")
    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = clean_text(og_title["content"])
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = clean_text(h1.get_text(" ", strip=True))

    desc = ""
    desc_meta = soup.find("meta", attrs={"name": "description"})
    if desc_meta and desc_meta.get("content"):
        desc = clean_text(desc_meta["content"])
    if not desc:
        paragraphs = []
        for p in soup.select("p"):
            p_text = clean_text(p.get_text(" ", strip=True))
            if len(p_text) >= 40:
                paragraphs.append(p_text)
            if len(paragraphs) >= 3:
                break
        desc = clean_text(" ".join(paragraphs))

    published = ""
    for attr in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("time", {}),
    ]:
        node = soup.find(attr[0], attrs=attr[1])
        if not node:
            continue
        if node.get("content"):
            published = clean_text(node["content"])
            break
        if node.get("datetime"):
            published = clean_text(node["datetime"])
            break
        published = clean_text(node.get_text(" ", strip=True))
        if published:
            break

    if not title:
        return {}
    return {
        "title": title[:220],
        "summary": desc[:500],
        "url": url,
        "source": source_name,
        "platform": platform,
        "published_at": published[:80],
    }


def extract_page_links(source: Dict[str, str], html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(source["url"]).netloc
    links = []
    seen = set()
    for a in soup.select("a[href]"):
        href = urljoin(source["url"], a.get("href", ""))
        if href in seen:
            continue
        if not looks_like_article(href, base_domain):
            continue
        title = clean_text(a.get_text(" ", strip=True))
        if len(title) < 12:
            continue
        seen.add(href)
        links.append(href)
        if len(links) >= source.get("limit", 6):
            break
    return links


def extract_markdown_links(source: Dict[str, str], text: str) -> List[str]:
    base_domain = urlparse(source["origin_url"]).netloc
    links = []
    seen = set()
    for title, href in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        href = clean_text(href)
        if href in seen:
            continue
        if not looks_like_article(href, base_domain):
            continue
        if len(clean_text(title)) < 12:
            continue
        seen.add(href)
        links.append(href)
        if len(links) >= source.get("limit", 6):
            break
    return links


def fetch_html_index(source: Dict[str, str]) -> List[Dict[str, str]]:
    urls = build_request_candidates(source["url"], allow_jina=False)
    try:
        html, _ = request_text_with_fallback(urls)
    except Exception:
        return []
    items = []
    for link in extract_page_links(source, html):
        snapshot = extract_article_snapshot(link, source["name"], source["platform"])
        if snapshot:
            items.append(snapshot)
    return items


def fetch_markdown_index(source: Dict[str, str]) -> List[Dict[str, str]]:
    markdown_url = source.get("fetch_url") or as_jina_url(source["url"])
    materialized = dict(source)
    materialized["origin_url"] = source["url"]
    try:
        text, _ = request_text_with_fallback([markdown_url])
    except Exception:
        return []
    items = []
    for link in extract_markdown_links(materialized, text):
        snapshot = extract_article_snapshot(link, source["name"], source["platform"])
        if snapshot:
            items.append(snapshot)
    return items


def fetch_rss_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        xml_text, _ = request_text_with_fallback(build_request_candidates(source["url"], allow_jina=False))
        root = ET.fromstring(xml_text)
    except Exception:
        return []
    items = []
    for item in root.findall(".//item")[: source.get("limit", 6)]:
        title = clean_text(item.findtext("title", ""))
        link = clean_text(item.findtext("link", ""))
        summary = clean_text(item.findtext("description", ""))
        published = clean_text(item.findtext("pubDate", ""))
        if not title or not link:
            continue
        items.append(
            {
                "title": title[:220],
                "summary": summary[:500],
                "url": link,
                "source": source["name"],
                "platform": source["platform"],
                "published_at": published[:80],
            }
        )
    return items


def fetch_atom_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        xml_text, _ = request_text_with_fallback(build_request_candidates(source["url"], allow_jina=False))
        root = ET.fromstring(xml_text)
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall(".//a:entry", ns)[: source.get("limit", 6)]:
        title = clean_text(entry.findtext("a:title", "", ns))
        summary = clean_text(entry.findtext("a:summary", "", ns))
        link = ""
        link_node = entry.find("a:link", ns)
        if link_node is not None:
            link = clean_text(link_node.attrib.get("href", ""))
        published = clean_text(entry.findtext("a:published", "", ns))
        if not title or not link:
            continue
        items.append(
            {
                "title": title[:220],
                "summary": summary[:500],
                "url": link,
                "source": source["name"],
                "platform": source["platform"],
                "published_at": published[:80],
            }
        )
    return items


def fetch_hn_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        ids = requests.get(source["url"], timeout=REQUEST_TIMEOUT).json()
    except Exception:
        return []
    items = []
    for story_id in ids[: source.get("scan_limit", 30)]:
        try:
            payload = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=REQUEST_TIMEOUT,
            ).json()
        except Exception:
            continue
        title = clean_text((payload or {}).get("title", ""))
        if not title:
            continue
        text_blob = clean_text(f"{title} {(payload or {}).get('text', '')}")
        if not is_ai_related(text_blob):
            continue
        items.append(
            {
                "title": title[:220],
                "summary": clean_text((payload or {}).get("text", ""))[:500],
                "url": (payload or {}).get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                "source": source["name"],
                "platform": source["platform"],
                "published_at": str((payload or {}).get("time", "")),
            }
        )
        if len(items) >= source.get("limit", 8):
            break
    return items


def fetch_redlib_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        html, _ = request_text_with_fallback([source["url"]])
    except Exception:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for post in soup.select("div.post")[: source.get("limit", 5)]:
        title_link = post.select_one("h2.post_title a[href*='/comments/']")
        if not title_link:
            continue
        title = clean_text(title_link.get_text(" ", strip=True))
        if is_low_value(title):
            continue
        summary = ""
        body = post.select_one("div.post_body")
        if body:
            summary = clean_text(body.get_text(" ", strip=True))[:500]
        created = post.select_one("span.created")
        published = clean_text(created.get("title", "") if created else "")
        href = title_link.get("href", "")
        items.append(
            {
                "title": title[:220],
                "summary": summary,
                "url": urljoin(source["url"], href),
                "source": source["name"],
                "platform": source["platform"],
                "published_at": published[:80],
            }
        )
    return items


def split_x_posts(text: str, source_url: str, source: Dict[str, str]) -> List[Dict[str, str]]:
    lines = [line.rstrip() for line in text.splitlines()]
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("## ") and "posts" in line.lower():
            start = i + 1
            break
    chunks: List[str] = []
    current: List[str] = []
    for raw in lines[start:]:
        line = clean_text(raw)
        if not line:
            if current:
                chunks.append(" ".join(current))
                current = []
            continue
        if line.startswith("[![") or line.startswith("!["):
            continue
        if any(
            line.startswith(prefix)
            for prefix in ["Quote", "Readers added context", "The media could not be played."]
        ):
            continue
        if line in {"OpenAI", "@OpenAI", "Sam Altman", "@sama"}:
            continue
        current.append(line)
    if current:
        chunks.append(" ".join(current))

    items = []
    for chunk in chunks:
        chunk = clean_text(chunk)
        if len(chunk) < 30:
            continue
        title = chunk.split(".")[0][:120]
        items.append(
            {
                "title": title,
                "summary": chunk[:500],
                "url": source_url,
                "source": source["name"],
                "platform": source["platform"],
                "published_at": "",
            }
        )
        if len(items) >= source.get("limit", 3):
            break
    return items


def fetch_x_jina_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        text, _ = request_text_with_fallback([as_jina_url(source["url"])])
    except Exception:
        return []
    return split_x_posts(text, source["url"], source)


def fetch_youtube_jina_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        text, _ = request_text_with_fallback([as_jina_url(source["url"])])
    except Exception:
        return []
    matches = re.findall(
        r"### \[([^\]]+)\]\((http://www\.youtube\.com/watch\?v=[^)]+)\s*(?:\"[^\"]*\")?\)",
        text,
    )
    items = []
    seen = set()
    for title, url in matches:
        clean_url = url.replace("http://", "https://").split(" ", 1)[0].strip()
        if url in seen:
            continue
        seen.add(clean_url)
        snapshot = extract_article_snapshot(clean_url, source["name"], source["platform"])
        if snapshot:
            items.append(snapshot)
        else:
            items.append(
                {
                    "title": clean_text(title)[:220],
                    "summary": "",
                    "url": clean_url,
                    "source": source["name"],
                    "platform": source["platform"],
                    "published_at": "",
                }
            )
        if len(items) >= source.get("limit", 5):
            break
    return items


def fetch_tiktok_items(source: Dict[str, str]) -> List[Dict[str, str]]:
    api_key = os.environ.get("TIKTOK_RAPIDAPI_KEY", "").strip()
    api_host = os.environ.get("TIKTOK_RAPIDAPI_HOST", "tiktok-api23.p.rapidapi.com").strip()
    if not api_key:
        return []
    endpoint = source.get("url", "https://tiktok-api23.p.rapidapi.com/api/search/video")
    items = []
    for keyword in source.get("keywords", [])[: source.get("max_keywords", 3)]:
        try:
            resp = requests.get(
                endpoint,
                params={"keywords": keyword, "count": source.get("per_keyword", 3), "cursor": 0},
                headers={"x-rapidapi-key": api_key, "x-rapidapi-host": api_host},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            continue
        for entry in payload.get("itemList", [])[: source.get("per_keyword", 3)]:
            desc = clean_text(entry.get("desc", ""))
            aweme_id = clean_text(entry.get("id", ""))
            author = (entry.get("author") or {}).get("uniqueId", "")
            url = f"https://www.tiktok.com/@{author}/video/{aweme_id}" if author and aweme_id else ""
            items.append(
                {
                    "title": (desc[:120] or f"TikTok: {keyword}")[:220],
                    "summary": desc[:500],
                    "url": url,
                    "source": source["name"],
                    "platform": source["platform"],
                    "published_at": str(entry.get("createTime", "")),
                }
            )
        if len(items) >= source.get("limit", 5):
            break
    return items[: source.get("limit", 5)]


def fetch_source(source: Dict[str, str]) -> List[Dict[str, str]]:
    fetch_type = source["type"]
    if fetch_type == "rss":
        return fetch_rss_items(source)
    if fetch_type == "atom":
        return fetch_atom_items(source)
    if fetch_type == "html_index":
        return fetch_html_index(source)
    if fetch_type == "markdown_index":
        return fetch_markdown_index(source)
    if fetch_type == "hn":
        return fetch_hn_items(source)
    if fetch_type == "redlib":
        return fetch_redlib_items(source)
    if fetch_type == "x_jina":
        return fetch_x_jina_items(source)
    if fetch_type == "youtube_jina":
        return fetch_youtube_jina_items(source)
    if fetch_type == "tiktok_rapidapi":
        return fetch_tiktok_items(source)
    return []


def is_ai_related(text: str) -> bool:
    haystack = (text or "").lower()
    return any(keyword in haystack for keyword in AI_KEYWORDS)


def score_item(item: Dict[str, str], focus: str) -> int:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    score = 0
    for keyword in AI_KEYWORDS:
        if keyword in text:
            score += 2
    if item.get("platform") in {"official", "media"}:
        score += 4
    elif item.get("platform") in {"research", "youtube", "x"}:
        score += 2
    if focus == "ecommerce":
        for word in ["ecommerce", "retail", "shopping", "commerce", "marketing", "sales"]:
            if word in text:
                score += 4
    elif focus == "research":
        for word in ["paper", "benchmark", "reasoning", "architecture", "arxiv", "training"]:
            if word in text:
                score += 4
    elif focus == "tools":
        for word in ["tool", "sdk", "api", "ide", "developer", "agent", "workflow", "plugin"]:
            if word in text:
                score += 4
    for word in ["release", "launch", "funding", "agent", "benchmark", "paper", "enterprise", "developer"]:
        if word in text:
            score += 1
    return score


def dedupe_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result = []
    for item in items:
        fingerprint = (item.get("url") or item.get("title") or "").strip().lower()
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(item)
    return result


def collect_candidates(focus: str, config: Dict) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for source in config.get("sources", []):
        if source.get("enabled", True) is False:
            continue
        items.extend(fetch_source(source))

    filtered = []
    for item in dedupe_items(items):
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if not is_ai_related(text):
            continue
        if is_low_value(text):
            continue
        item["score"] = score_item(item, focus)
        filtered.append(item)
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    return filtered[: config.get("max_candidates", 60)]


def summarize_platform_counts(candidates: List[Dict[str, str]]) -> str:
    counts: Dict[str, int] = {}
    for item in candidates:
        counts[item.get("platform", "other")] = counts.get(item.get("platform", "other"), 0) + 1
    return json.dumps(counts, ensure_ascii=False)


def build_system_prompt(skill_content: str) -> str:
    return f"""你是一位专业 AI 资讯编辑。你只能基于我提供的候选素材写日报，不能虚构新事实。

以下是技能定义，请严格遵守其筛选和排版要求：

{skill_content}

额外要求：
1. 全文中文。
2. 只保留信息密度高、与 AI 主线强相关的内容。
3. 摘要必须具体，不要泛泛而谈。
4. 每条深度报道必须包含：深度摘要、关键判断、对我的帮助。
5. X 至少优先使用 10-15 条高价值帖子；YouTube 优先使用 5 条内最有价值的视频；其余平台宁缺毋滥。
"""


def build_user_prompt(target_date: str, focus: str, candidates: List[Dict[str, str]]) -> str:
    focus_instruction = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS[""])
    payload = json.dumps(candidates, ensure_ascii=False, indent=2)
    platform_stats = summarize_platform_counts(candidates)
    return f"""请基于以下候选素材，生成 {target_date} 的 AI 每日日报。

时间范围：以 {target_date} 为主的最近 24 小时公开信息。
聚焦方向：{focus_instruction}
当前候选平台分布：{platform_stats}

写作要求：
- 按 SKILL 模板输出 Markdown
- 保留最有价值的内容并去重
- 重点关注：AI 底层逻辑、商业落地、应用、使用方法、电商应用、未来趋势、最新发布
- 官方发布、研究突破、商业落地优先
- 不要编造候选中不存在的发布日期、数据或观点
- 如果候选里某个平台质量低，可以少写，但不要用无关信息凑数

候选素材如下：
{payload}

直接输出最终 Markdown，不要添加额外说明。"""


def generate_daily(target_date: str, focus: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少环境变量 DEEPSEEK_API_KEY")

    config = load_json(CONFIG_PATH)
    candidates = collect_candidates(focus, config)
    if not candidates:
        raise RuntimeError("未抓取到可用候选内容，请检查网络或数据源")

    client = OpenAI(api_key=api_key, base_url=DEFAULT_BASE_URL)
    skill = load_skill()
    print(f"🔍 已抓取候选内容 {len(candidates)} 条，开始调用 DeepSeek 生成日报...", flush=True)

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": build_system_prompt(skill)},
            {"role": "user", "content": build_user_prompt(target_date, focus, candidates)},
        ],
        max_tokens=7000,
    )
    content = response.choices[0].message.content if response.choices else ""
    content = content.strip() if content else ""
    if not content:
        raise RuntimeError("DeepSeek 返回内容为空")
    return content


def save_output(content: str, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"💾 已保存至：{output_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 每日日报生成器（DeepSeek 版）")
    parser.add_argument("--date", default="", help="目标日期 YYYY-MM-DD，留空为今天")
    parser.add_argument("--focus", default="", help="聚焦方向：ecommerce/research/tools")
    parser.add_argument("--output", default="", help="输出文件路径")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    output_path = args.output or f"reports/AI日报_{target_date}.md"
    content = generate_daily(target_date, args.focus)
    save_output(content, output_path)
    print(f"📰 AI日报_{target_date}.md 生成完毕", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ 生成失败：{exc}", file=sys.stderr)
        sys.exit(1)
