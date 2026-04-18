"""
fetcher_twitter.py — X/Twitter AI 舆情抓取（twitterapi.io）

流程：
1. 获取 @yy9752245942576 的关注列表（AI 权威博主名单）
2. 逐账号抓取最新推文
3. 过滤非 AI 内容
4. 按互动量（点赞 + 转发 × 3）降序返回 Top 20
"""

import os
import re
import time
import hashlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "new1_0645634567c24fafa75da544ca1b5be0")
TWITTER_BASE = "https://api.twitterapi.io"
SOURCE_USER = "yy9752245942576"

# AI 关键词白名单（匹配推文文本）
_AI_KEYWORDS = frozenset([
    "ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic", "deepseek",
    "mistral", "llama", "qwen", "agent", "rag", "sora", "diffusion", "transformer",
    "multimodal", "agi", "benchmark", "hugging face", "fine-tun", "embedding",
    "inference", "alignment", "reinforcement learning", "prompt", "lora", "vllm",
    "chatgpt", "copilot", "cursor", "replit", "langchain", "llamaindex", "autogen",
    "o1", "o3", "o4", "gpt-4", "gpt-5", "claude 3", "claude 4", "gemini 2",
    "人工智能", "大模型", "智能体", "语言模型", "生成式", "神经网络",
])


# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────
def _mk_id(url: str, text: str) -> str:
    return hashlib.md5(f"{url}{text[:80]}".encode()).hexdigest()[:12]


def _is_ai_related(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _AI_KEYWORDS)


def _parse_dt(s: str) -> Optional[datetime]:
    """解析多种 Twitter 日期格式"""
    if not s:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S +0000 %Y",  # v1 标准格式
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _headers() -> dict:
    return {"X-API-Key": TWITTER_API_KEY, "Content-Type": "application/json"}


# ─────────────────────────────────────────────
#  API 调用
# ─────────────────────────────────────────────
def _get_followings(username: str, max_users: int = 200) -> list[dict]:
    """获取指定用户的关注列表，支持翻页"""
    url = f"{TWITTER_BASE}/twitter/user/followings"
    all_users: list[dict] = []
    cursor: Optional[str] = None

    for _ in range(5):  # 最多 5 页
        params: dict = {"userName": username, "count": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=25)
            if r.status_code != 200:
                logger.warning(f"Twitter followings {r.status_code}: {r.text[:300]}")
                break
            data = r.json()
            # 兼容 twitterapi.io 多种响应结构
            users = (
                data.get("users")
                or data.get("data", {}).get("users", [])
                or []
            )
            if isinstance(users, dict):
                users = list(users.values()) if users else []
            all_users.extend(users)
            if len(all_users) >= max_users:
                break
            # 翻页 cursor
            cursor = data.get("next_cursor") or data.get("data", {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"_get_followings error: {e}")
            break

    logger.info(f"  Following list: {len(all_users)} accounts")
    return all_users[:max_users]


def _get_user_tweets(username: str, cutoff: datetime) -> list[dict]:
    """获取单个账号的最新 AI 相关推文"""
    url = f"{TWITTER_BASE}/twitter/user/tweets"
    params = {"userName": username, "count": 20}
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        raw = (
            data.get("tweets")
            or data.get("data", {}).get("tweets", [])
            or []
        )
        if isinstance(raw, dict):
            raw = raw.get("tweets", [])

        results = []
        for t in raw:
            text = t.get("text") or t.get("full_text") or ""
            if not text or not _is_ai_related(text):
                continue

            # 时效过滤
            created = t.get("createdAt") or t.get("created_at") or ""
            pub_dt = _parse_dt(created)
            if pub_dt and pub_dt < cutoff:
                continue

            tweet_id = str(t.get("id") or t.get("id_str") or "")
            tweet_url = f"https://x.com/{username}/status/{tweet_id}" if tweet_id else ""

            # 互动指标（兼容多种字段名）
            m = t.get("public_metrics") or {}
            likes = int(
                m.get("like_count")
                or t.get("likeCount")
                or t.get("favorite_count")
                or 0
            )
            rts = int(
                m.get("retweet_count")
                or t.get("retweetCount")
                or t.get("retweet_count")
                or 0
            )
            views = int(
                m.get("impression_count")
                or t.get("viewCount")
                or t.get("view_count")
                or 0
            )

            # 清理推文文本（去掉 URL）
            clean_text = re.sub(r"https?://\S+", "", text).strip()
            display = clean_text[:200] if clean_text else text[:200]

            results.append({
                "id": _mk_id(tweet_url, text),
                "source_id": "twitter_x",
                "source_name": f"X · @{username}",
                "category": "X/Twitter",
                "priority": 1,
                "title": display,
                "url": tweet_url,
                "summary": text[:500],
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "author": username,
                "likes": likes,
                "retweets": rts,
                "views": views,
            })
        return results

    except Exception as e:
        logger.warning(f"  _get_user_tweets @{username}: {e}")
        return []


# ─────────────────────────────────────────────
#  主入口
# ─────────────────────────────────────────────
def fetch_twitter(cutoff_hours: int = 48, max_accounts: int = 50) -> list[dict]:
    """
    抓取 @yy9752245942576 关注列表中 AI 权威博主的最新 AI 相关推文。
    返回按互动量降序排列的 Top 20 条目。
    """
    if not TWITTER_API_KEY:
        logger.info("TWITTER_API_KEY not set, skipping Twitter fetch")
        return []

    logger.info(f"Fetching X/Twitter following list of @{SOURCE_USER} ...")
    following = _get_followings(SOURCE_USER, max_users=max_accounts)
    if not following:
        logger.warning("Twitter: empty following list, skipping")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
    all_tweets: list[dict] = []
    seen: set[str] = set()

    for i, user in enumerate(following[:max_accounts]):
        username = (
            user.get("screen_name")
            or user.get("userName")
            or user.get("username")
            or ""
        )
        if not username:
            continue

        tweets = _get_user_tweets(username, cutoff)
        for tw in tweets:
            if tw["id"] not in seen:
                seen.add(tw["id"])
                all_tweets.append(tw)

        time.sleep(0.3)

    # 按互动热度排序（转发权重 ×3，浏览量加成）
    all_tweets.sort(
        key=lambda x: x.get("likes", 0) + x.get("retweets", 0) * 3 + x.get("views", 0) // 100,
        reverse=True,
    )
    logger.info(f"Twitter: collected {len(all_tweets)} AI tweets → returning top 20")
    return all_tweets[:20]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = fetch_twitter(cutoff_hours=48, max_accounts=5)
    import json
    print(json.dumps(results[:3], ensure_ascii=False, indent=2))
