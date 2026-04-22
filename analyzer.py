"""
analyzer.py — DeepSeek AI 深度解读模块（优化版）

流程：
1. 本地规则快速预过滤（零 API 调用）：关键词权重打分，过滤无关内容
2. 按来源优先级 + 本地评分，取 TOP 40 候选
3. 对 TOP 40 用 DeepSeek 批量评分（每批30条，1-2次请求）
4. 对最终精选 12 条做深度解读
5. 生成今日导语

总 API 调用：~15次（原来 1345次 → 15次，节省99%时间）
"""

import os
import re
import json
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  DeepSeek 客户端
# ─────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-486e1846d4e140b486cf9bfad64c9dd2")
DEEPSEEK_MODEL = "deepseek-chat"

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)


def _call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> str:
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
            logger.warning(f"DeepSeek attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)
    return ""


# ─────────────────────────────────────────────
#  Step 1：本地规则预过滤（零 API）
# ─────────────────────────────────────────────

HIGH_VALUE_KW = [
    "gpt", "claude", "gemini", "llm", "large language model",
    "transformer", "diffusion", "multimodal", "vision language",
    "reasoning", "agent", "rag", "fine-tun", "lora", "rlhf", "alignment",
    "openai", "anthropic", "deepmind", "mistral", "meta ai", "deepseek",
    "hugging face", "open source", "benchmark", "sora", "video generation",
    "code generation", "text to", "image generation", "foundation model",
    "inference", "quantiz", "context window", "token", "embedding",
    "safety", "hallucin", "jailbreak", "prompt", "chain of thought",
    "neural", "dataset", "evaluation", "sota", "state of the art",
    "model", "ai ", " ai", "machine learning", "deep learning",
]

LOW_VALUE_KW = [
    "hiring", "job posting", "we're hiring", "conference registration",
    "workshop deadline", "call for paper", "submission deadline",
    "cookie", "privacy policy", "terms of service",
]

HIGH_PRIORITY_SOURCES = {
    "openai_blog": 4, "anthropic_blog": 4, "deepmind_blog": 4,
    "mistral_blog": 3, "huggingface_blog": 3, "the_batch": 3,
    "import_ai": 3, "github_trending": 2, "hackernews_ai": 1,
    "paperswithcode": 2,
}


def _local_score(item: dict) -> int:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    score = 3

    source_id = item.get("source_id", "")
    score += HIGH_PRIORITY_SOURCES.get(source_id, 0)

    kw_hits = sum(1 for kw in HIGH_VALUE_KW if kw in text)
    score += min(kw_hits, 4)

    noise_hits = sum(1 for kw in LOW_VALUE_KW if kw in text)
    score -= noise_hits * 2

    title = item.get("title", "")
    if len(title) < 10 or len(title) > 200:
        score -= 1

    return max(0, min(10, score))


def prefilter(items: list[dict], top_n: int = 40) -> list[dict]:
    """本地预过滤，返回最有价值的 top_n 条"""
    for item in items:
        item["local_score"] = _local_score(item)

    filtered = [i for i in items if i["local_score"] >= 4]

    # 每个来源最多取 5 条
    source_count: dict[str, int] = {}
    candidates = []
    for item in sorted(filtered, key=lambda x: x["local_score"], reverse=True):
        sid = item.get("source_id", "")
        if source_count.get(sid, 0) < 5:
            candidates.append(item)
            source_count[sid] = source_count.get(sid, 0) + 1
        if len(candidates) >= top_n:
            break

    logger.info(f"  本地预过滤: {len(items)} → {len(candidates)} 条候选")
    return candidates


# ─────────────────────────────────────────────
#  Step 2：DeepSeek 批量评分（每批30条，1-2次API）
# ─────────────────────────────────────────────

BATCH_SCORE_SYSTEM = """你是AI领域资深编辑。对以下新闻的「AI前沿价值」打分（0-10）。

评分标准：
- 9-10：颠覆性突破（新旗舰模型发布、重大架构创新）
- 7-8：重要进展（重要工具开源、权威报告、关键研究）
- 5-6：有参考价值（技术更新、应用案例）
- 3-4：普通资讯
- 0-2：广告/招聘/与AI无关

只返回JSON数组，格式：[{"id":"xxx","score":8}, ...]
不要任何其他内容。"""


def batch_score(candidates: list[dict]) -> list[dict]:
    """批量评分，每批30条"""
    if not candidates:
        return candidates

    batch_size = 30
    scored_map: dict[str, int] = {}

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        items_text = "\n".join(
            f'{{"id":"{item["id"]}","title":"{item["title"][:80].replace(chr(34), chr(39))}","src":"{item["source_name"]}"}}'
            for item in batch
        )
        raw = _call_deepseek(BATCH_SCORE_SYSTEM, items_text, max_tokens=600)
        try:
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                for s in scores:
                    scored_map[str(s["id"])] = int(s.get("score", 5))
        except Exception as e:
            logger.warning(f"Batch score parse failed: {e} | raw: {raw[:200]}")

        time.sleep(0.5)

    for item in candidates:
        item["score"] = scored_map.get(item["id"], item.get("local_score", 5))

    return candidates


# ─────────────────────────────────────────────
#  Step 3：深度解读（逐条，仅精选12条）
# ─────────────────────────────────────────────

ANALYSIS_SYSTEM = """你是顶级AI技术分析师，面向中文读者（AI从业者/创业者）撰写深度解读。

按以下结构输出（总200-300字）：

**核心亮点**
1-2句说明最重要的技术/产品突破。

**为什么重要**
对AI领域的意义：技术进步、行业影响。

**实用价值**
对AI工具用户/开发者/创业者的直接帮助，可用场景。

**延伸思考**
一句趋势判断或展望。

语言：简洁专业，不说废话，避免营销腔。"""


def analyze_item(item: dict) -> dict:
    prompt = (
        f"来源：{item['source_name']}\n"
        f"标题：{item['title']}\n"
        f"摘要：{item.get('summary','')[:400]}\n\n"
        f"请生成中文深度解读。"
    )
    item["analysis"] = _call_deepseek(ANALYSIS_SYSTEM, prompt, max_tokens=500)
    time.sleep(0.5)
    return item


# ─────────────────────────────────────────────
#  Step 4：今日导语
# ─────────────────────────────────────────────

SUMMARY_SYSTEM = """你是AI日报主编，写一段今日导语（150-200字）。

要求：
1. 提炼今日2-3个核心AI趋势/事件
2. 点出最值得关注的开源项目或工具
3. 一句话点评今天整体AI生态动向
4. 语气：专业有温度，像给朋友写的行业简报
5. 直接写流畅段落，不要标题/分段"""


def generate_daily_summary(top_items: list[dict]) -> str:
    headlines = "\n".join(
        f"- [{item['source_name']}] {item['title']}（{item.get('score',5)}分）"
        for item in top_items[:15]
    )
    return _call_deepseek(SUMMARY_SYSTEM, f"今日精选：\n{headlines}", max_tokens=350)


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
DEEP_N = 12
QUICK_N = 8


def analyze_all(items: list[dict]) -> dict:
    logger.info(f"  原始条目：{len(items)} 条")

    # 1. 本地预过滤（零API）
    candidates = prefilter(items, top_n=40)

    # 2. DeepSeek 批量评分（1-2次API调用）
    logger.info(f"  DeepSeek 批量评分 {len(candidates)} 条候选 ...")
    candidates = batch_score(candidates)
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 3. 多样性选取精选
    deep_pool: list[dict] = []
    cat_quota: dict[str, int] = {}
    for item in candidates:
        cat = item.get("category", "其他")
        if cat_quota.get(cat, 0) < 3 and len(deep_pool) < DEEP_N:
            deep_pool.append(item)
            cat_quota[cat] = cat_quota.get(cat, 0) + 1

    # 4. 逐条深度解读（~12次API）
    logger.info(f"  深度解读 {len(deep_pool)} 条 ...")
    deep_analyzed = [analyze_item(item) for item in deep_pool]

    # 5. 快讯
    deep_ids = {i["id"] for i in deep_pool}
    quick_items = [i for i in candidates if i["id"] not in deep_ids][:QUICK_N]

    # 6. 今日导语（1次API）
    logger.info("  生成今日导语 ...")
    daily_summary = generate_daily_summary(deep_analyzed + quick_items)

    logger.info(f"  ✅ 完成：{len(deep_analyzed)} 条深度解读，{len(quick_items)} 条快讯")

    return {
        "daily_summary": daily_summary,
        "deep_items": deep_analyzed,
        "quick_items": quick_items,
        "total_fetched": len(items),
        "total_filtered": len(candidates),
    }
