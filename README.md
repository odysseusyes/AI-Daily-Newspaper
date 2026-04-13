# 🤖 AI 前沿日报

> 每日自动抓取 12 个权威 AI 信息源，DeepSeek AI 深度解读，每天早上 08:00 自动推送到 GitHub。

[![Daily Report](https://github.com/odysseusyes/AI-Daily-Newspaper/actions/workflows/daily.yml/badge.svg)](https://github.com/odysseusyes/AI-Daily-Newspaper/actions/workflows/daily.yml)

---

## 📋 信息源覆盖

| 分类 | 信息源 |
|------|--------|
| 🤖 大模型动态 | OpenAI Blog · Anthropic Blog · Google DeepMind · Mistral AI |
| 📄 论文研究 | arXiv (AI/CV/ML) · Papers With Code |
| 🛠️ 开源工具 | Hugging Face Blog · GitHub Trending AI |
| 💡 行业观点 | The Batch (Andrew Ng) · Import AI (Jack Clark) |
| 💬 社区讨论 | Hacker News AI 精选 |

---

## 🧠 AI 解读流程

```
多源抓取 (12源) → DeepSeek 评分(0-10) → 过滤低质量 → 深度解读(精选12条) → 快讯(8条) → 渲染HTML → 发布GitHub
```

每条深度解读包含：
- **核心亮点** — 技术/产品突破
- **为什么重要** — 行业影响
- **实用价值** — 对 AI 从业者的直接帮助
- **延伸思考** — 趋势预判

---

## 🚀 部署步骤（5分钟完成）

### 1. Fork / Clone 此仓库

```bash
git clone https://github.com/odysseusyes/AI-Daily-Newspaper.git
cd AI-Daily-Newspaper
```

### 2. 配置 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|-------------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（必填） |

> `GITHUB_TOKEN` 由 GitHub Actions 自动提供，无需手动配置。

### 3. 开启 GitHub Pages

**Settings → Pages → Source → Deploy from a branch → 选择 `main` 分支 `/docs` 目录**

### 4. 触发首次运行

**Actions → 📰 AI 日报自动生成 → Run workflow**

首次运行约需 3-5 分钟。完成后可访问：

```
https://<你的用户名>.github.io/AI-Daily-Newspaper/
```

---

## 📅 自动调度

- **时间**：每天 UTC 00:00 = 北京时间 08:00
- **平台**：GitHub Actions（免费，无需服务器）
- **通知**：每次生成后自动创建 GitHub Issue，Watch 仓库即可收到邮件通知

**订阅方式**：点击仓库右上角 **Watch → Custom → Issues** ✓ 即可每天收到邮件。

---

## 🛠️ 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export DEEPSEEK_API_KEY="sk-xxxx"
export GITHUB_TOKEN="ghp_xxxx"
export GITHUB_REPO="odysseusyes/AI-Daily-Newspaper"

# 本地测试（不发布）
python main.py --dry-run

# 正常运行
python main.py
```

---

## 📁 项目结构

```
.
├── main.py              # 主入口
├── fetcher.py           # 多源抓取（RSS + GitHub API）
├── analyzer.py          # DeepSeek AI 评分 + 深度解读
├── renderer.py          # HTML + Markdown 渲染
├── publisher.py         # GitHub 自动发布
├── requirements.txt     # Python 依赖
├── .github/
│   └── workflows/
│       └── daily.yml    # GitHub Actions 调度
├── docs/                # GitHub Pages（日报 HTML）
│   ├── index.html       # 最新日报
│   └── archive.json     # 历史归档索引
└── reports/             # Markdown 版本归档
```

---

*Powered by DeepSeek AI · 自动生成，每日更新*
