# 🤖 AI Daily Skill — 每日 AI 日报自动化系统

每天北京时间 **08:20** 自动生成最新动态日报，
由 DeepSeek API + 公开网页抓取生成高密度中文日报，
并直接提交到 GitHub 仓库的 `reports/` 目录。

---

## 当前部署位置

本机已部署到：

`/Users/ye/Documents/Codex/ai-daily-skill`

如果你要启用云端定时推送，需要把这个目录推到一个 GitHub 仓库，再配置 Secrets。

---

## 📁 目录结构

```
ai-daily-skill/
├── skills/ai-daily/
│   └── SKILL.md              # 技能定义（可直接用于 Claude Code / Codex）
├── .github/workflows/
│   └── daily.yml             # GitHub Actions 定时任务
├── config/
│   └── sources.json          # 平台与来源配置
├── scripts/
│   ├── generate_daily.py     # 抓多平台公开源并调用 DeepSeek 生成日报
│   └── push_to_obsidian.py   # 可选：如后续需要再接入 Obsidian
├── reports/                  # 每日日报归档（会自动提交到仓库）
├── requirements.txt
└── README.md
```

---

## 🚀 快速部署（10 分钟完成）

### 第一步：Fork 仓库

Fork 本项目到你的 GitHub 账号。

---

### 第二步：配置 GitHub Secrets

在 GitHub 仓库 → **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 | 必填 |
|------------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | ✅ 必填 |
| `TWITTERAPI_KEY` | twitterapi.io 的 X API Key（启用可核验时间的 X 抓取） | 可选 |
| `TIKTOK_RAPIDAPI_KEY` | TikTok RapidAPI Key（启用 TikTok 补充源） | 可选 |
| `TIKTOK_RAPIDAPI_HOST` | TikTok RapidAPI Host，默认 `tiktok-api23.p.rapidapi.com` | 可选 |

> **获取 GitHub Token：**
> Settings → Developer settings → Personal access tokens → Generate new token
> 勾选 `repo` 权限即可

---

### 第三步：启用 Actions

1. 进入仓库 → **Actions** 标签页
2. 点击 **"I understand my workflows, go ahead and enable them"**
3. 手动触发一次测试：Actions → **AI Daily Digest** → **Run workflow**

---

## ⚡ 手动触发参数

| 参数 | 说明 | 示例 |
|-----|------|------|
| `date` | 指定输出文件日期，留空=今天 | `2026-04-09` |
| `focus` | 聚焦方向 | `ecommerce` / `research` / `tools` |
| `preview_only` | 保留参数，当前纯 GitHub 版忽略 | `true` |

---

## 🔧 本地运行（可选）

```bash
# 克隆项目
git clone https://github.com/你的用户名/ai-daily-skill.git
cd ai-daily-skill

# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export DEEPSEEK_API_KEY="sk-..."

# 生成今日日报
python scripts/generate_daily.py --output reports/AI日报_$(date +%Y-%m-%d).md
```

---

## 📱 Claude Code / Codex 直接使用

将 `skills/ai-daily/SKILL.md` 放入你的 Skills 目录：

```bash
# Claude Code
cp -r skills/ai-daily ~/.claude/skills/

# 然后在 Claude Code 中
/ai-daily
```

---

## 📊 日报结构

每份日报包含：

- **🔥 今日重点判断 TOP5** — 5 条核心事件排序
- **🐦 X / Twitter 重点舆情** — 固定专栏，优先保留白名单账号中的高价值动态
- **📺 YouTube 核心内容** — 固定专栏，优先保留白名单频道中的高价值视频
- **📌 TechCrunch 深度文章** — 固定专栏，输出深度摘要 + 关键判断 + 行动建议
- **📰 其他平台深度报道** — 官方博客、研究和权威媒体的补充深度内容
- **⚡ 其他平台快讯** — 3 句话内的补充动态

时效规则：

- 每天 **08:20 CST** 自动运行一次
- 主窗口为：**当前生成时刻往前 36 小时**
- 平台补位窗口：
  - `X / Reddit / TikTok`：48 小时
  - `YouTube`：72 小时
- 例如：`2026-04-25 08:20` 生成时，主窗口覆盖 `2026-04-23 20:20` 到 `2026-04-25 08:20`
- 超出对应窗口的旧内容直接丢弃；如果窗口内可核验内容不足，任务失败，不凑数

---

## 🔑 数据源覆盖

**媒体 / 官方 / 研究**
- NYTimes Technology
- TechCrunch AI
- The Verge AI
- VentureBeat AI
- MIT Technology Review AI
- Google Developers Blog
- Google Cloud Blog
- OpenAI News
- Anthropic News
- Google DeepMind Blog
- Meta AI Blog
- Hugging Face Papers
- arXiv（cs.AI / cs.CL / cs.LG）

**社区 / 社媒 / 视频**
- Hacker News
- Reddit（通过 Redlib 镜像）
- X（`twitterapi.io` 优先，`r.jina.ai` 回退）
- YouTube（通过 `r.jina.ai` 代理）
- Product Hunt AI
- TikTok（可选，需 RapidAPI Key）

> 当前实现已经接入 X / Reddit / YouTube / Product Hunt。若配置 `TWITTERAPI_KEY`，X 会优先使用带 `createdAt` 的 API 结果；TikTok 需要额外 Secret 才会返回内容。

---

## 💡 常见问题

**Q：现在默认用什么模型？**
A：默认用 `deepseek-chat`。如需切换，可在环境变量里设置 `DEEPSEEK_MODEL`。

**Q：每次大概消耗多少 Token？**
A：取决于当天抓到的候选条目数量。当前实现是“脚本抓源 + DeepSeek 归纳”，通常比直接联网搜索更可控。

**Q：日报没有推送成功怎么排查？**
A：先看 `生成 AI 日报` 和 `提交日报到仓库` 两步；若仓库里已有 `reports/AI日报_YYYY-MM-DD.md`，说明成功。

---

## 📄 License

MIT License
