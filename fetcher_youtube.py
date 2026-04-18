"""
fetcher_youtube.py — YouTube AI Agent / 大模型精选视频

流程：
1. 用 yt-dlp 搜索多组 AI 关键词，汇总候选视频
2. 综合评分（播放量 × 新鲜度 × 互动度）
3. 对得分最高的视频获取完整元数据 + 字幕
4. 返回 1 条「本日精选」供 AI 深度解读
"""

import math
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# AI 相关搜索词（覆盖 Agent / 大模型 / 前沿研究）
SEARCH_QUERIES = [
    "AI agent autonomous 2025",
    "large language model new release 2025",
    "AI research breakthrough 2025",
    "GPT Claude Gemini latest update",
    "LLM agent framework tutorial",
    "multimodal AI model explained",
]

MAX_CANDIDATES = 50   # 候选池上限
CUTOFF_DAYS = 7       # 视频发布时效（天）


# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────
def _vid_hash(vid_id: str) -> str:
    return hashlib.md5(vid_id.encode()).hexdigest()[:12]


def _parse_upload_date(s: str) -> Optional[datetime]:
    """解析 yt-dlp 的 upload_date: YYYYMMDD"""
    if s and len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _score(entry: dict, now: datetime) -> float:
    """
    综合评分 (0-10):
      播放量 (0-5)  + 新鲜度 (0-4) + 互动度 (0-1)
    """
    views = int(entry.get("view_count") or 0)
    likes = int(entry.get("like_count") or 0)
    upload_date = entry.get("upload_date", "")

    # 播放量：对数缩放，100k+ 接近满分
    view_score = min(5.0, math.log10(max(views, 10)) - 1.0) if views > 0 else 0.0

    # 新鲜度：7 天内线性递减
    pub_dt = _parse_upload_date(upload_date)
    if pub_dt:
        days_old = max(0.0, (now - pub_dt).total_seconds() / 86400)
        fresh_score = max(0.0, 4.0 * (1.0 - days_old / CUTOFF_DAYS))
    else:
        fresh_score = 1.5  # 无日期信息给中等分

    # 互动度：点赞对数
    engage_score = min(1.0, math.log10(max(likes, 1)) * 0.4) if likes > 0 else 0.0

    return view_score + fresh_score + engage_score


# ─────────────────────────────────────────────
#  yt-dlp 搜索
# ─────────────────────────────────────────────
def _search(query: str, n: int = 8) -> list[dict]:
    """使用 yt-dlp 搜索 YouTube，flat 模式（快速）"""
    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
            return info.get("entries") or []
    except Exception as e:
        logger.warning(f"yt-dlp search '{query}': {e}")
        return []


def _get_full_info(video_id: str) -> dict:
    """获取单个视频的完整元数据（含 description / like_count 等）"""
    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            return info or {}
    except Exception as e:
        logger.warning(f"yt-dlp full info {video_id}: {e}")
        return {}


# ─────────────────────────────────────────────
#  字幕抓取
# ─────────────────────────────────────────────
def _get_transcript(video_id: str, max_chars: int = 4000) -> Optional[str]:
    """
    获取视频字幕，优先顺序：
    1. 手动英文字幕  2. 自动英文字幕  3. 手动中文字幕  4. None
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        tl = YouTubeTranscriptApi.list_transcripts(video_id)

        # 优先手动字幕
        for lang_list in (["en", "en-US", "en-GB"], ["zh", "zh-Hans", "zh-Hant"]):
            try:
                t = tl.find_manually_created_transcript(lang_list)
                segs = t.fetch()
                return " ".join(s["text"] for s in segs)[:max_chars]
            except Exception:
                pass

        # 退而求自动字幕
        for lang_list in (["en", "en-US"],):
            try:
                t = tl.find_generated_transcript(lang_list)
                segs = t.fetch()
                return " ".join(s["text"] for s in segs)[:max_chars]
            except Exception:
                pass

        return None
    except Exception as e:
        logger.warning(f"Transcript {video_id}: {e}")
        return None


# ─────────────────────────────────────────────
#  主入口
# ─────────────────────────────────────────────
def fetch_youtube(cutoff_hours: int = 168) -> list[dict]:
    """
    搜索 AI Agent / 大模型最新 YouTube 视频，返回最值得研究的 Top-1 视频。
    cutoff_hours 默认 168h（7 天），给视频时间积累播放量。
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=cutoff_hours)

    # ── Step 1: 多关键词搜索，汇聚候选池 ──
    candidates: dict[str, dict] = {}
    for query in SEARCH_QUERIES:
        entries = _search(query, n=8)
        for e in entries:
            vid_id = e.get("id") or ""
            if vid_id and vid_id not in candidates:
                candidates[vid_id] = e
        time.sleep(0.4)

    if not candidates:
        logger.warning("YouTube: no candidates found")
        return []

    logger.info(f"YouTube: {len(candidates)} candidates collected")

    # ── Step 2: 过滤时效 + 评分 ──
    scored: list[tuple[str, dict, float]] = []
    for vid_id, entry in candidates.items():
        pub_dt = _parse_upload_date(entry.get("upload_date", ""))
        if pub_dt and pub_dt < cutoff:
            continue
        s = _score(entry, now)
        scored.append((vid_id, entry, s))

    if not scored:
        logger.warning("YouTube: no recent videos after time filter")
        return []

    scored.sort(key=lambda x: x[2], reverse=True)
    vid_id, flat_entry, score = scored[0]
    logger.info(f"YouTube top: [{score:.2f}] {flat_entry.get('title', '')[:70]}")

    # ── Step 3: 获取完整元数据 ──
    full = _get_full_info(vid_id)
    title = full.get("title") or flat_entry.get("title") or ""
    channel = (
        full.get("uploader") or full.get("channel")
        or flat_entry.get("uploader") or flat_entry.get("channel") or ""
    )
    description = (full.get("description") or flat_entry.get("description") or "")[:600]
    views = int(full.get("view_count") or flat_entry.get("view_count") or 0)
    likes = int(full.get("like_count") or flat_entry.get("like_count") or 0)
    upload_date = full.get("upload_date") or flat_entry.get("upload_date") or ""
    pub_dt = _parse_upload_date(upload_date)

    # ── Step 4: 抓取字幕 ──
    transcript = _get_transcript(vid_id)
    logger.info(f"YouTube transcript: {'✅ ' + str(len(transcript)) + ' chars' if transcript else '❌ not available'}")

    return [{
        "id": _vid_hash(vid_id),
        "source_id": "youtube",
        "source_name": f"YouTube · {channel}",
        "category": "YouTube",
        "priority": 1,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={vid_id}",
        "summary": description,
        "published_at": pub_dt.isoformat() if pub_dt else None,
        "view_count": views,
        "like_count": likes,
        "channel": channel,
        "transcript": transcript,
        "youtube_score": round(score, 2),
    }]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = fetch_youtube()
    if results:
        r = results[0]
        print(f"Title: {r['title']}")
        print(f"Channel: {r['channel']}")
        print(f"Views: {r['view_count']:,}")
        print(f"Score: {r['youtube_score']}")
        print(f"Transcript: {len(r['transcript'] or '')} chars")
