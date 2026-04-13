"""
publisher.py — GitHub 自动发布模块

功能：
1. 将生成的 HTML 日报提交到 GitHub 仓库（docs/ 目录）
2. 更新 docs/index.html（最新日报）
3. 更新 docs/archive.json（历史归档索引）
4. 自动创建 GitHub Issue（作为订阅通知）
"""

import os
import json
import base64
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  配置（从环境变量读取）
# ─────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")   # e.g. "odysseusyes/AI-Daily-Newspaper"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
API_BASE = "https://api.github.com"


# ─────────────────────────────────────────────
#  GitHub API 工具函数
# ─────────────────────────────────────────────
def _get_file_sha(repo: str, path: str) -> str | None:
    """获取文件的 SHA（用于更新时需要）"""
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=HEADERS, params={"ref": GITHUB_BRANCH})
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def _put_file(repo: str, path: str, content: str, message: str) -> bool:
    """创建或更新文件"""
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    sha = _get_file_sha(repo, path)
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=HEADERS, json=payload)
    if resp.status_code in (200, 201):
        logger.info(f"✅ GitHub: {path} updated")
        return True
    logger.error(f"❌ GitHub put failed [{resp.status_code}]: {resp.text[:300]}")
    return False


def _create_issue(repo: str, title: str, body: str) -> str | None:
    """创建 GitHub Issue（作为订阅通知）"""
    url = f"{API_BASE}/repos/{repo}/issues"
    payload = {
        "title": title,
        "body": body,
        "labels": ["daily-news", "automated"],
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if resp.status_code == 201:
        issue_url = resp.json().get("html_url")
        logger.info(f"✅ Issue created: {issue_url}")
        return issue_url
    logger.warning(f"Issue create failed [{resp.status_code}]: {resp.text[:200]}")
    return None


# ─────────────────────────────────────────────
#  归档索引管理
# ─────────────────────────────────────────────
def _update_archive(repo: str, date_str: str, html_path: str, issue_url: str | None) -> None:
    """更新 docs/archive.json 归档索引"""
    archive_path = "docs/archive.json"
    sha = _get_file_sha(repo, archive_path)
    archive = []

    if sha:
        url = f"{API_BASE}/repos/{repo}/contents/{archive_path}"
        resp = requests.get(url, headers=HEADERS, params={"ref": GITHUB_BRANCH})
        if resp.status_code == 200:
            raw = base64.b64decode(resp.json()["content"]).decode("utf-8")
            try:
                archive = json.loads(raw)
            except Exception:
                archive = []

    # 插入新条目（最多保留 90 天）
    entry = {
        "date": date_str,
        "html_path": html_path,
        "issue_url": issue_url or "",
    }
    archive.insert(0, entry)
    archive = archive[:90]

    _put_file(repo, archive_path, json.dumps(archive, ensure_ascii=False, indent=2),
              f"📚 Archive update · {date_str}")


# ─────────────────────────────────────────────
#  生成 Archive 导航页
# ─────────────────────────────────────────────
ARCHIVE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AI 日报归档</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family:'PingFang SC',sans-serif; max-width:700px; margin:0 auto; padding:40px 20px; }}
  h1 {{ font-size:1.8rem; margin-bottom:8px; }}
  p {{ color:#94a3b8; margin-bottom:32px; font-size:14px; }}
  .list {{ list-style:none; padding:0; }}
  .list li {{ border-bottom:1px solid #1e293b; padding:12px 0; display:flex; justify-content:space-between; align-items:center; }}
  a {{ color:#6366f1; text-decoration:none; font-weight:600; }}
  a:hover {{ text-decoration:underline; }}
  .date {{ font-size:13px; color:#94a3b8; }}
</style>
</head>
<body>
<h1>🤖 AI 前沿日报归档</h1>
<p>每日自动更新 · DeepSeek AI 深度解读</p>
<ul class="list">
{items}
</ul>
</body>
</html>"""


def _generate_archive_page(archive: list[dict], repo: str) -> str:
    items_html = ""
    for entry in archive[:60]:
        date = entry.get("date", "")
        html_path = entry.get("html_path", "")
        # GitHub Pages URL
        page_url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/{html_path}"
        items_html += f'  <li><a href="{page_url}">{date} 日报</a><span class="date">{date}</span></li>\n'
    return ARCHIVE_PAGE_TEMPLATE.format(items=items_html)


# ─────────────────────────────────────────────
#  主发布函数
# ─────────────────────────────────────────────
def publish(html_content: str, md_content: str, data: dict, date_str: str) -> dict:
    """
    发布日报到 GitHub
    返回发布结果 {html_url, issue_url, success}
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning("GITHUB_TOKEN or GITHUB_REPO not set, skipping publish")
        return {"success": False, "html_url": "", "issue_url": ""}

    # 文件路径
    date_slug = date_str.replace(" ", "-").replace("/", "-")
    html_file = f"docs/{date_slug}.html"
    md_file = f"reports/{date_slug}.md"

    success = True

    # 1. 上传日期 HTML
    ok1 = _put_file(GITHUB_REPO, html_file, html_content,
                    f"📰 AI 日报 · {date_str}")
    if not ok1:
        success = False

    # 2. 更新 docs/index.html（最新日报 = 首页）
    ok2 = _put_file(GITHUB_REPO, "docs/index.html", html_content,
                    f"🏠 Update index · {date_str}")
    if not ok2:
        success = False

    # 3. 上传 Markdown 版本
    _put_file(GITHUB_REPO, md_file, md_content,
              f"📝 MD Report · {date_str}")

    # 4. 创建 GitHub Issue 作为订阅通知
    summary = data.get("daily_summary", "")[:300]
    deep_count = len(data.get("deep_items", []))
    issue_title = f"📰 AI 日报 · {date_str} ({deep_count} 条深度解读)"
    issue_body = (
        f"## 今日导语\n\n{summary}\n\n---\n\n"
        f"📊 本期统计：抓取 {data.get('total_fetched', 0)} 条 → "
        f"AI 筛选 {data.get('total_filtered', 0)} 条 → "
        f"深度解读 {deep_count} 条\n\n"
        f"🔗 [查看完整日报](https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}/{html_file})\n\n"
        f"*由 DeepSeek AI 自动生成*"
    )
    issue_url = _create_issue(GITHUB_REPO, issue_title, issue_body)

    # 5. 更新归档索引
    _update_archive(GITHUB_REPO, date_str, html_file, issue_url)

    pages_url = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}/{html_file}"

    return {
        "success": success,
        "html_url": pages_url,
        "issue_url": issue_url or "",
        "html_file": html_file,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Publisher module loaded. Set GITHUB_TOKEN and GITHUB_REPO to test.")
