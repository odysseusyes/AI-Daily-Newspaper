"""
renderer.py — HTML 日报渲染模块

输出一个精美的单文件 HTML（可在浏览器直接打开，也可作为 GitHub Pages 页面），
同时输出 Markdown 版本（用于 GitHub 仓库 issues 或 README）。
"""

import re
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
#  颜色 / 图标映射
# ─────────────────────────────────────────────
CATEGORY_CONFIG = {
    "大模型动态": {"icon": "🤖", "color": "#6366f1"},
    "论文研究":   {"icon": "📄", "color": "#0ea5e9"},
    "开源工具":   {"icon": "🛠️", "color": "#10b981"},
    "行业观点":   {"icon": "💡", "color": "#f59e0b"},
    "社区讨论":   {"icon": "💬", "color": "#8b5cf6"},
    "其他":       {"icon": "📌", "color": "#6b7280"},
}

SCORE_LABEL = {
    range(9, 11): ("🔥 顶级", "#ef4444"),
    range(7, 9):  ("⭐ 重要", "#f59e0b"),
    range(5, 7):  ("📌 关注", "#6366f1"),
}


def _score_badge(score: int) -> tuple[str, str]:
    for r, (label, color) in SCORE_LABEL.items():
        if score in r:
            return label, color
    return ("📋 参考", "#9ca3af")


def _markdown_to_html(text: str) -> str:
    """简单的 Markdown -> HTML 转换（加粗/换行）"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = text.replace('\n', '<br>')
    return text


# ─────────────────────────────────────────────
#  HTML 模板
# ─────────────────────────────────────────────
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 日报 · {date_str}</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #273344;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #6366f1;
    --border: #334155; --radius: 12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'PingFang SC','Helvetica Neue',sans-serif; line-height: 1.7; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* ── 顶部 Header ── */
  .header {{
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 40px 24px 32px;
    text-align: center;
  }}
  .header-badge {{
    display: inline-block; background: var(--accent);
    color: #fff; font-size: 12px; font-weight: 700;
    padding: 4px 12px; border-radius: 999px; letter-spacing: .05em;
    margin-bottom: 14px;
  }}
  .header h1 {{ font-size: 2rem; font-weight: 800; letter-spacing: -.02em; }}
  .header .subtitle {{ color: var(--muted); font-size: 14px; margin-top: 6px; }}
  .stats {{ display: flex; justify-content: center; gap: 24px; margin-top: 20px; flex-wrap: wrap; }}
  .stat {{ text-align: center; }}
  .stat-n {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
  .stat-l {{ font-size: 12px; color: var(--muted); }}

  /* ── 导语 ── */
  .summary-box {{
    max-width: 860px; margin: 32px auto; padding: 0 20px;
  }}
  .summary-card {{
    background: linear-gradient(135deg, #1e1b4b 0%, #1e293b 100%);
    border: 1px solid #4338ca44;
    border-radius: var(--radius); padding: 24px 28px;
  }}
  .summary-title {{ font-size: 13px; font-weight: 700; color: #818cf8; letter-spacing: .1em; margin-bottom: 12px; }}
  .summary-text {{ font-size: 15px; line-height: 1.8; color: #c7d2fe; }}

  /* ── 主体内容 ── */
  .main {{ max-width: 860px; margin: 0 auto; padding: 0 20px 60px; }}
  .section-title {{
    display: flex; align-items: center; gap: 10px;
    font-size: 13px; font-weight: 700; color: var(--muted);
    letter-spacing: .1em; text-transform: uppercase;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px; margin: 36px 0 20px;
  }}
  .section-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }}

  /* ── 深度解读卡片 ── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 24px;
    margin-bottom: 16px;
    transition: border-color .2s;
  }}
  .card:hover {{ border-color: #6366f166; }}
  .card-meta {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  .badge {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; font-weight: 600; padding: 3px 9px;
    border-radius: 999px; white-space: nowrap;
  }}
  .card-title {{ font-size: 16px; font-weight: 700; margin-bottom: 4px; }}
  .card-title a {{ color: var(--text); }}
  .card-title a:hover {{ color: var(--accent); }}
  .card-source {{ font-size: 12px; color: var(--muted); margin-bottom: 14px; }}
  .analysis {{
    background: var(--surface2); border-radius: 8px;
    padding: 16px 18px; font-size: 14px; color: #cbd5e1; line-height: 1.8;
    border-left: 3px solid var(--accent);
  }}
  .analysis strong {{ color: #e2e8f0; }}

  /* ── 快讯列表 ── */
  .quick-item {{
    display: flex; align-items: flex-start; gap: 12px;
    padding: 14px 0; border-bottom: 1px solid var(--border);
  }}
  .quick-item:last-child {{ border-bottom: none; }}
  .quick-num {{ font-size: 12px; color: var(--muted); min-width: 20px; margin-top: 2px; }}
  .quick-body {{ flex: 1; }}
  .quick-title {{ font-size: 14px; font-weight: 600; color: var(--text); }}
  .quick-title a {{ color: var(--text); }}
  .quick-title a:hover {{ color: var(--accent); }}
  .quick-reason {{ font-size: 12px; color: var(--muted); margin-top: 3px; }}

  /* ── Footer ── */
  .footer {{
    text-align: center; font-size: 12px; color: var(--muted);
    padding: 24px; border-top: 1px solid var(--border);
  }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-badge">AI DAILY NEWS</div>
  <h1>🤖 AI 前沿日报</h1>
  <p class="subtitle">{date_str} · DeepSeek 深度解读 · 每日 08:00 自动更新</p>
  <div class="stats">
    <div class="stat"><div class="stat-n">{total_sources}</div><div class="stat-l">信息源</div></div>
    <div class="stat"><div class="stat-n">{total_fetched}</div><div class="stat-l">抓取条目</div></div>
    <div class="stat"><div class="stat-n">{total_filtered}</div><div class="stat-l">AI 筛选</div></div>
    <div class="stat"><div class="stat-n">{deep_count}</div><div class="stat-l">深度解读</div></div>
  </div>
</div>

<!-- DAILY SUMMARY -->
<div class="summary-box">
  <div class="summary-card">
    <div class="summary-title">✦ 今日导语</div>
    <div class="summary-text">{daily_summary}</div>
  </div>
</div>

<!-- MAIN -->
<div class="main">

  <!-- 深度解读 -->
  <div class="section-title"><span class="section-dot"></span>深度解读 · 精选 {deep_count} 条</div>
  {deep_cards_html}

  <!-- 快讯 -->
  {quick_section_html}

</div>

<!-- FOOTER -->
<div class="footer">
  由 DeepSeek AI 自动生成 · 数据来源：arXiv / OpenAI / Anthropic / DeepMind / Hugging Face / GitHub Trending 等 {total_sources} 个权威源<br>
  生成时间：{generated_at}
</div>

</body>
</html>
"""


def _render_deep_card(item: dict, idx: int) -> str:
    cat = item.get("category", "其他")
    cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["其他"])
    score = item.get("score", 5)
    badge_label, badge_color = _score_badge(score)
    analysis_html = _markdown_to_html(item.get("analysis", "（暂无解读）"))
    pub = item.get("published_at", "")[:10] if item.get("published_at") else ""

    return f"""
  <div class="card">
    <div class="card-meta">
      <span class="badge" style="background:{cfg['color']}22;color:{cfg['color']}">{cfg['icon']} {cat}</span>
      <span class="badge" style="background:{badge_color}22;color:{badge_color}">{badge_label} {score}/10</span>
    </div>
    <div class="card-title"><a href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a></div>
    <div class="card-source">来源：{item['source_name']}{f' · {pub}' if pub else ''}</div>
    <div class="analysis">{analysis_html}</div>
  </div>"""


def _render_quick_section(quick_items: list[dict]) -> str:
    if not quick_items:
        return ""
    items_html = ""
    for i, item in enumerate(quick_items, 1):
        cat = item.get("category", "其他")
        cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["其他"])
        reason = item.get("score_reason", "")
        items_html += f"""
    <div class="quick-item">
      <div class="quick-num">{i:02d}</div>
      <div class="quick-body">
        <div class="quick-title">
          <span style="color:{cfg['color']}">{cfg['icon']}</span>
          <a href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a>
        </div>
        <div class="quick-reason">{item['source_name']}{f' · {reason}' if reason else ''}</div>
      </div>
    </div>"""

    return f"""
  <div class="section-title"><span class="section-dot" style="background:#f59e0b"></span>今日快讯</div>
  {items_html}"""


def render_html(data: dict, date_str: str | None = None) -> str:
    """渲染完整 HTML 日报"""
    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)
    date_str = date_str or now.strftime("%Y年%m月%d日 %A")

    deep_items = data.get("deep_items", [])
    quick_items = data.get("quick_items", [])

    deep_cards_html = "".join(
        _render_deep_card(item, i + 1) for i, item in enumerate(deep_items)
    )
    quick_section_html = _render_quick_section(quick_items)

    return HTML_TEMPLATE.format(
        date_str=date_str,
        total_sources=12,
        total_fetched=data.get("total_fetched", 0),
        total_filtered=data.get("total_filtered", 0),
        deep_count=len(deep_items),
        daily_summary=data.get("daily_summary", "").replace("\n", "<br>"),
        deep_cards_html=deep_cards_html,
        quick_section_html=quick_section_html,
        generated_at=now.strftime("%Y-%m-%d %H:%M CST"),
    )


# ─────────────────────────────────────────────
#  Markdown 版本（用于 GitHub Issues / README）
# ─────────────────────────────────────────────
def render_markdown(data: dict, date_str: str | None = None) -> str:
    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)
    date_str = date_str or now.strftime("%Y-%m-%d")

    lines = [
        f"# 🤖 AI 前沿日报 · {date_str}",
        "",
        "> DeepSeek AI 深度解读 · 自动生成",
        "",
        "## 今日导语",
        "",
        data.get("daily_summary", ""),
        "",
        "---",
        "",
        "## 深度解读",
        "",
    ]

    for i, item in enumerate(data.get("deep_items", []), 1):
        cat = item.get("category", "其他")
        cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["其他"])
        score = item.get("score", 5)
        lines += [
            f"### {i}. {item['title']}",
            "",
            f"**来源：** {item['source_name']}  |  **分类：** {cfg['icon']} {cat}  |  **评分：** {score}/10",
            "",
            f"🔗 [{item['url']}]({item['url']})",
            "",
            item.get("analysis", ""),
            "",
            "---",
            "",
        ]

    if data.get("quick_items"):
        lines += ["## 今日快讯", ""]
        for item in data["quick_items"]:
            reason = item.get("score_reason", "")
            lines.append(f"- [{item['title']}]({item['url']}) — {item['source_name']}{f'  *{reason}*' if reason else ''}")
        lines += ["", "---", ""]

    lines += [
        f"*生成时间：{now.strftime('%Y-%m-%d %H:%M CST')}  |  数据来源：12 个权威 AI 信息源*",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    # 测试渲染
    test_data = {
        "daily_summary": "今天是一个测试导语，用于验证渲染效果。",
        "deep_items": [{
            "id": "t1", "source_name": "OpenAI Blog", "category": "大模型动态",
            "title": "GPT-5 Released", "url": "https://openai.com",
            "score": 10, "score_reason": "颠覆性发布",
            "analysis": "**核心亮点**\nGPT-5 发布了。\n\n**为什么重要**\n这很重要。",
            "published_at": "2026-04-13T00:00:00+00:00",
        }],
        "quick_items": [],
        "total_fetched": 100, "total_filtered": 30,
    }
    html = render_html(test_data)
    with open("/tmp/test_render.html", "w") as f:
        f.write(html)
    print("Rendered to /tmp/test_render.html")
