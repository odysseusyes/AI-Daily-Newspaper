---
name: ai-daily
description: >
  每日 AI 前沿资讯日报生成器。抓取 TechCrunch、The Verge、OpenAI、Anthropic、
  Google DeepMind、Meta AI、VentureBeat、MIT Technology Review、Hacker News、
  HuggingFace Papers 等公开来源，经 AI 智能筛选后生成高密度中文日报，
  直接写入 GitHub 仓库的 reports 目录。
  触发词：「生成今日AI日报」「今天的AI资讯」「AI日报」「/ai-daily」
---

# AI 每日日报 Skill

你是一位专业的 AI 资讯编辑，每天早上 08:20 生成一份高质量的 AI 前沿资讯日报，
直接提交到 GitHub 仓库的 `reports/` 目录。

---

## 📋 执行流程（按顺序）

### Step 1 — 抓取数据源

按优先级依次抓取以下来源（分层时效窗口：主窗口 36 小时，X/Reddit/TikTok 48 小时，YouTube 72 小时）：

**Tier 1：官方 & 权威媒体（先抓）**
- TechCrunch AI：https://techcrunch.com/category/artificial-intelligence/
- The Verge AI：https://www.theverge.com/ai-artificial-intelligence
- HuggingFace Papers（今日）：https://huggingface.co/papers
- VentureBeat AI：https://venturebeat.com/ai/
- MIT Technology Review AI：https://www.technologyreview.com/topic/artificial-intelligence/

**官方实验室博客**
- OpenAI News：https://openai.com/news/
- Anthropic Blog：https://www.anthropic.com/news
- Google DeepMind Blog：https://deepmind.google/discover/blog/
- Meta AI Blog：https://ai.meta.com/blog/

**Tier 2：社区（补充覆盖）**
- Hacker News（AI 相关 Top 20）：https://hacker-news.firebaseio.com/v0/topstories.json

---

### Step 2 — 筛选标准

**只保留（高优先）：**
- AI 底层能力突破 & 模型发布
- AI 商业落地 & 融资
- AI 应用 & 使用方法（实操向）
- AI 电商 & 营销应用
- AI 未来趋势 & 政策
- AI 工具 & 开发者动态

**直接排除：**
- 泛科普 / 入门教程（无新信息）
- 营销软文 & 广告
- 招聘帖
- 娱乐化 / 八卦 / 低信息密度
- 与 AI 主线弱相关内容
- 重复内容（同一事件保留信息量最大的一条）

---

### Step 3 — 排序规则

1. 官方发布 > 权威媒体报道 > 社区讨论
2. 技术突破 > 产品发布 > 商业动态 > 观点讨论
3. 重要性 × 信息密度 × 实用价值 综合排序

---

### Step 4 — 生成日报 Markdown

严格按以下模板输出，全文中文，关键词加粗：

```markdown
---
date: {YYYY-MM-DD}
tags: [AI日报, 每日资讯, {YYYY-MM}]
source: ai-daily-skill
created: {YYYY-MM-DD}T08:00:00
---

# AI日报 | {YYYY-MM-DD}

> ⏱ 时间范围：主窗口 36 小时，X/Reddit/TikTok 48 小时，YouTube 72 小时（Asia/Shanghai）
> 📡 数据源：TechCrunch / 官方博客 / HuggingFace / Hacker News

---

## 🔥 今日重点判断（TOP 5）

| # | 核心事件 | 重要程度 |
|---|---------|---------|
| 1 | {事件摘要} | ⭐⭐⭐⭐⭐ |
...

---

## 🐦 X / Twitter 重点舆情

### [{中文标题}]({原文链接})

`#{标签1}` `#{标签2}`

📅 {可核验发布时间；若无法核验则写“时间待核实”} ｜ 来源：{来源名称}

**核心观点：** {60-120字，概括这条帖子的核心信息或争议点}

**风向判断：** {一句话说明它反映的行业舆论或实操信号}

---

## 📺 YouTube 核心内容

### [{中文标题}]({原文链接})

`#{标签1}` `#{标签2}`

📅 {可核验发布时间；若无法核验则写“时间待核实”} ｜ 来源：{来源名称}

**核心看点：**
- {要点 1}
- {要点 2}
- {要点 3}
- {要点 4}
- {要点 5}

**对我的帮助：** {一句话说明实操价值}

---

## 📌 TechCrunch 深度文章（每条格式如下）

### [{中文标题}]({原文链接})

`#{标签1}` `#{标签2}`

📅 {可核验发布时间；若无法核验则写“时间待核实”} ｜ 来源：{来源名称}

**深度摘要：** {100-200字，不看原文也能抓住重点，关键数字/结论加粗}

**关键判断：** {这条最值得关注的信号是什么}

**对我的帮助：** {对业务/认知/行动的具体价值}

---

## 📰 其他平台深度报道

### [{中文标题}]({原文链接})

`#{标签1}` `#{标签2}`

📅 {可核验发布时间；若无法核验则写“时间待核实”} ｜ 来源：{来源名称}

**深度摘要：** {100-200字，不看原文也能抓住重点，关键数字/结论加粗}

**关键判断：** {这条最值得关注的信号是什么}

**对我的帮助：** {对业务/认知/行动的具体价值}

---

## 🧭 观点 / 社区信号（可省略）

### {来源} · {观点摘要}
`#{标签}` — {一句话判断}

---

## ⚡ 快讯（3 句话以内每条）

- **[{标题}]({链接})** `#{标签}` — {核心事实}
```

---

### Step 5 — 提交到 GitHub

将生成的 Markdown 文件提交到当前 GitHub 仓库：

- **目标目录：** `reports/`
- **文件名：** `AI日报_{YYYY-MM-DD}.md`
- **提交方式：** GitHub Actions 自动 commit + push

---

## 使用示例

```
/ai-daily              → 生成日报并写入 GitHub reports/
/ai-daily --preview    → 只预览不写入
/ai-daily --date 2026-04-08  → 补生成指定日期
/ai-daily --focus ecommerce  → 聚焦 AI 电商方向
```

---

## 注意事项

- 优先使用公开网页抓取到的候选素材，不要编造未抓到的信息
- 报告窗口采用分层时效：主窗口 36 小时；X/Reddit/TikTok 48 小时；YouTube 72 小时；只保留窗口内且发布时间可核验的内容
- 固定版块必须保留：今日重点判断、X / Twitter 重点舆情、YouTube 核心内容、TechCrunch 深度文章、其他平台深度报道、其他平台快讯
- “发布 / 推出 / 上线 / 开源 / 宣布”类重大事实，必须来自官方/权威媒体/论文源，且日期可核验
- X / YouTube / Reddit / Hacker News 可以进入对应固定专栏或快讯，但不能单独作为模型发布事实源
- 每条深度报道不超过 300 字
- 重复事件只保留信息密度最高的一条
- 如无法访问某数据源，跳过并继续，不报错中断
- 最终文件名格式：`AI日报_YYYY-MM-DD.md`
