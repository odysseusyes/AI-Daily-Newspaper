"""
main.py — AI 前沿日报 · 主入口

运行方式：
  python main.py              # 正常生成并发布
  python main.py --dry-run    # 只生成 HTML，不发布到 GitHub
  python main.py --local      # 生成并保存到本地 output/ 目录
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fetcher import fetch_all
from analyzer import analyze_all
from renderer import render_html, render_markdown
from publisher import publish

# ─────────────────────────────────────────────
#  日志配置
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ─────────────────────────────────────────────
#  日期工具
# ─────────────────────────────────────────────
def get_date_str() -> str:
    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)
    weekday = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    return now.strftime(f"%Y年%m月%d日 周{weekday}")


def get_date_slug() -> str:
    tz_cn = timezone(timedelta(hours=8))
    return datetime.now(tz_cn).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def run(dry_run: bool = False, local: bool = False) -> None:
    date_str = get_date_str()
    date_slug = get_date_slug()
    logger.info(f"═══════════════════════════════════════")
    logger.info(f"  AI 前沿日报  ·  {date_str}")
    logger.info(f"═══════════════════════════════════════")

    # ── Step 1: 抓取 ──────────────────────────
    logger.info("📡 Step 1: 抓取多源 AI 资讯 ...")
    items = fetch_all(cutoff_hours=26)
    logger.info(f"  抓取完成：{len(items)} 条")

    if not items:
        logger.warning("  ⚠️  没有抓取到任何内容，退出")
        sys.exit(1)

    # ── Step 2: AI 评分 + 深度解读 ────────────
    logger.info("🧠 Step 2: DeepSeek AI 评分与解读 ...")
    data = analyze_all(items)
    logger.info(
        f"  分析完成：精选 {len(data['deep_items'])} 条深度解读，"
        f"{len(data['quick_items'])} 条快讯"
    )

    # ── Step 3: 渲染 HTML + Markdown ─────────
    logger.info("🎨 Step 3: 渲染日报 ...")
    html_content = render_html(data, date_str)
    md_content = render_markdown(data, date_slug)
    logger.info("  渲染完成")

    # ── Step 4: 保存 / 发布 ───────────────────
    if local or dry_run:
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        html_path = out_dir / f"{date_slug}.html"
        md_path = out_dir / f"{date_slug}.md"
        data_path = out_dir / f"{date_slug}_data.json"

        html_path.write_text(html_content, encoding="utf-8")
        md_path.write_text(md_content, encoding="utf-8")
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"📁 Step 4: 已保存到本地")
        logger.info(f"  → {html_path}")
        logger.info(f"  → {md_path}")

        if dry_run:
            logger.info("  Dry-run 模式，不发布到 GitHub")
            return

    if not dry_run:
        logger.info("🚀 Step 4: 发布到 GitHub ...")
        result = publish(html_content, md_content, data, date_slug)
        if result["success"]:
            logger.info(f"  ✅ 发布成功！")
            logger.info(f"  🌐 日报页面: {result['html_url']}")
            if result.get("issue_url"):
                logger.info(f"  📌 Issue: {result['issue_url']}")
        else:
            logger.error("  ❌ 发布失败，请检查 GITHUB_TOKEN 和 GITHUB_REPO 配置")
            sys.exit(1)

    logger.info("═══════════════════════════════════════")
    logger.info("  ✅ 日报生成完成！")
    logger.info("═══════════════════════════════════════")


# ─────────────────────────────────────────────
#  CLI 入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI 前沿日报生成器")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成文件，不发布到 GitHub（同时保存到 output/）")
    parser.add_argument("--local", action="store_true",
                        help="生成并保存到本地 output/ 目录，然后发布到 GitHub")
    args = parser.parse_args()

    run(dry_run=args.dry_run, local=args.local)
