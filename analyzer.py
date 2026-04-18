"""
analyzer.py — DeepSeek AI 深度解读模块

功能：
1. 对每条新闻生成中文深度解读（重要性 / 技术亮点 / 实用价值）
2. 对全部新闻做一次"今日总结"，提炼核心趋势
3. 自动对新闻评分，过滤低质量内容
"""

import os
import json
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  DeepSeek 客户端（兼容 OpenAI SDK）
# ─────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-486e1846d4e140b486cf9bfad64c9dd2")
DEEPSEEK_MODEL = "deepseek-chat"

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)


def _call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    """调用 DeepSeek API，带重试"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.4,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"DeepSeek API attempt {attempt + 1} failed: {e}")
            time.sleep(2 ** attempt)
    return "（AI 解读暂时不可用）"


# ─────────────────────────────────────────────
#  单条新闻评分 + 过滤
# ─────────────────────────────────────────────
SCORE_SYSTEM = """你是一位 AI 领域资深编辑，专注于大模型、AI 工具、AI 应用落地。
请对下面这条新闻/论文/项目的「AI 前沿价值」打分（0-10分），并用一句话说明理由。
打分标准：
- 10分：颠覆性突破（如 GPT-4 发布、全新架构）
- 7-9分：重要进展（新模型、重要工具开源、权威报告）
- 4-6分：有参考价值（技术更新、应用案例）
- 1-3分：普通资讯、广告软文、重复内容
- 0分：与 AI 无关

只返回 JSON：{"score": <int>, "reason": "<一句话>"}"""


def score_item(item: dict) -> dict:
    """给单条新闻打分，返回添加了 score 和 score_reason 的 item"""
    prompt = f"标题：{item['title']}\n摘要：{item.get('summary', '')[:300]}\n来源：{item['source_name']}"
    raw = _call_deepseek(SCORE_SYSTEM, prompt, max_tokens=120)
    try:
        data = json.loads(raw)
        item["score"] = int(data.get("score", 5))
        item["score_reason"] = data.get("reason", "")
    except Exception:
        item["score"] = 5
        item["score_reason"] = ""
    return item


# ─────────────────────────────────────────────
#  单条新闻深度解读
# ─────────────────────────────────────────────
ANALYSIS_SYSTEM = """你是一位顶级 AI 技术分析师，面向中文读者（AI 从业者 / 创业者）撰写深度资讯解读。

对每条新闻，请按以下结构输出（总字数 200-350 字）：

**核心亮点**
用 1-2 句话说明这条消息最重要的技术/产品突破是什么。

**为什么重要**
解释这对 AI 领域的意义：技术层面的进步、对现有方案的超越、行业影响。

**实用价值**
这对 AI 工具使用者 / 开发者 / 创业者有什么直接帮助？能用在哪些场景？

**延伸思考**
一句话的判断或展望（趋势预判、潜在风险、值得关注的后续）。

语言要求：简洁专业、不说废话、避免营销腔。"""


def analyze_item(item: dict) -> dict:
    """对单条新闻生成深度解读"""
    prompt = (
        f"来源：{item['source_name']}\n"
        f"标题：{item['title']}\n"
        f"原文摘要：{item.get('summary', '')[:500]}\n\n"
        f"请生成中文深度解读。"
    )
    item["analysis"] = _call_deepseek(ANALYSIS_SYSTEM, prompt, max_tokens=600)
    time.sleep(0.3)  # 避免 QPS 超限
    return item


# ─────────────────────────────────────────────
#  今日总结（编辑导语）
# ─────────────────────────────────────────────
SUMMARY_SYSTEM = """你是 AI 日报主编，每天撰写一段精炼的"今日导语"（150-250 字）。

要求：
1. 提炼今日最核心的 2-3 个 AI 趋势/事件
2. 指出今天最值得关注的开源项目或工具
3. 用一句话点评今天的整体 AI 生态动向
4. 语气：专业、有温度、像给朋友写的行业简报
5. 不要使用标题/分段，直接写成流畅的段落"""


def generate_daily_summary(top_items: list[dict]) -> str:
    """根据评分最高的新闻生成今日总结"""
    headlines = "\n".join(
        f"- [{item['source_name']}] {item['title']}（分数:{item.get('score', 5)}）"
        for item in top_items[:15]
    )
    prompt = f"今日精选新闻列表：\n{headlines}\n\n请生成今日导语。"
    return _call_deepseek(SUMMARY_SYSTEM, prompt, max_tokens=400)


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
MIN_SCORE = 5       # 低于此分数的内容被过滤
TOP_N = 12          # 每日精选条数上限（深度解读）
QUICK_N = 8         # 快讯条数（只显示标题+评分理由，不做深度解读）


def analyze_all(items: list[dict]) -> dict:
    """
    对所有抓取内容进行：评分 → 过滤 → 精选深度解读 → 生成导语
    返回结构化日报数据
    """
    logger.info(f"Scoring {len(items)} items ...")
    scored = []
    for item in items:
        scored_item = score_item(item)
        scored.append(scored_item)
        logger.debug(f"  [{scored_item['score']}] {scored_item['title'][:60]}")

    # 按分数排序，过滤低质量
    filtered = [i for i in scored if i.get("score", 0) >= MIN_SCORE]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 按分类分组
    categories: dict[str, list] = {}
    for item in filtered:
        cat = item.get("category", "其他")
        categories.setdefault(cat, []).append(item)

    # 精选 TOP_N 条做深度解读（来自不同分类，优先高分）
    deep_pool: list[dict] = []
    cat_quota: dict[str, int] = {}
    for item in filtered:
        cat = item.get("category", "其他")
        if cat_quota.get(cat, 0) < 3 and len(deep_pool) < TOP_N:
            deep_pool.append(item)
            cat_quota[cat] = cat_quota.get(cat, 0) + 1

    logger.info(f"Deep analyzing {len(deep_pool)} top items ...")
    deep_analyzed = []
    for item in deep_pool:
        analyzed = analyze_item(item)
        deep_analyzed.append(analyzed)

    # 快讯：剩余内容（不做深度解读）
    deep_ids = {i["id"] for i in deep_pool}
    quick_items = [i for i in filtered if i["id"] not in deep_ids][:QUICK_N]

    # 今日总结
    logger.info("Generating daily summary ...")
    daily_summary = generate_daily_summary(deep_analyzed + quick_items)

    return {
        "daily_summary": daily_summary,
        "deep_items": deep_analyzed,          # 深度解读
        "quick_items": quick_items,            # 快讯
        "total_fetched": len(items),
        "total_filtered": len(filtered),
    }


# ─────────────────────────────────────────────
#  YouTube 视频深度解读（3-5 核心观点）
# ─────────────────────────────────────────────
YOUTUBE_SYSTEM = """你是顶级 AI 研究分析师，专门从 YouTube 视频中提炼核心洞见，面向中文读者（AI 从业者/研究者/创业者）。

请根据视频标题、简介和字幕，输出以下内容（总字数 350-500 字）：

**📌 视频价值定位**
一句话说明这个视频的核心价值和目标受众。

**🔑 核心观点**
逐条列出 3-5 个关键洞见，每条格式：
① **[观点标题]** — 具体论述（1-2 句，含论据/数据）

**💬 关键引用**
摘录视频中 1-3 句最有价值的原话或核心判断（意译，保持准确）。

**🎯 对 AI 从业者的启示**
2-3 句，说明这个视频对开发者/研究者/创业者的直接实用价值。

语言要求：简洁专业，信息密度高，避免废话和营销腔。"""


def analyze_youtube_video(item: dict) -> dict:
    """
    对 YouTube 精选视频生成深度解读。
    利用字幕 + 简介 + 元数据，由 DeepSeek 提炼 3-5 核心观点。
    """
    transcript = (item.get("transcript") or "")[:3000]
    description = (item.get("summary") or "")[:500]
    views = item.get("view_count", 0)
    likes = item.get("like_count", 0)
    pub_date = (item.get("published_at") or "")[:10]

    parts = [
        f"**视频标题：** {item['title']}",
        f"**频道：** {item.get('channel', 'N/A')}",
        f"**播放量：** {views:,}  |  **点赞：** {likes:,}  |  **发布：** {pub_date or 'N/A'}",
    ]
    if description:
        parts.append(f"\n**视频简介（节选）：**\n{description}")
    if transcript:
        parts.append(f"\n**字幕内容（节选 {len(transcript)} 字）：**\n{transcript}")
    else:
        parts.append("\n（注：字幕不可用，基于标题与简介进行分析）")

    prompt = "\n".join(parts) + "\n\n请提炼核心观点。"
    item["analysis"] = _call_deepseek(YOUTUBE_SYSTEM, prompt, max_tokens=900)
    return item


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 测试用假数据
    test_items = [
        {
            "id": "test001",
            "source_id": "openai_blog",
            "source_name": "OpenAI Blog",
            "category": "大模型动态",
            "priority": 1,
            "title": "Introducing GPT-4o: Our Most Advanced Model Yet",
            "url": "https://openai.com/blog/gpt-4o",
            "summary": "OpenAI releases GPT-4o, a new model that processes text, audio, and images natively.",
            "published_at": None,
        }
    ]
    result = analyze_all(test_items)
    print(json.dumps(result, ensure_ascii=False, indent=2))
