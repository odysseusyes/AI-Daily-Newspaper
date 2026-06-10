# CLAUDE.md

Guidance for AI assistants (Claude Code and others) working in this repository.

## What this project is

**AI 前沿日报 (AI Frontier Daily)** is a zero-server, fully automated pipeline that
every morning at **08:00 Beijing time (UTC 00:00)**:

1. Fetches AI news from ~13 authoritative sources (RSS + GitHub API),
2. Scores and deep-analyzes the items with the **DeepSeek** LLM,
3. Renders a polished single-file HTML report plus a Markdown version, and
4. Publishes everything back to this GitHub repo (commits + GitHub Pages + a notification Issue).

It runs entirely on GitHub Actions — there is no backend server. The published
site is served via **GitHub Pages from the `/docs` directory**.

## Architecture & data flow

The pipeline is four sequential stages, orchestrated by `main.py`:

```
fetcher.fetch_all()  →  analyzer.analyze_all()  →  renderer.render_html/markdown()  →  publisher.publish()
   (RSS + GitHub)         (DeepSeek scoring)            (HTML + MD strings)              (GitHub Contents API)
```

| File | Responsibility | Key entry point |
|------|----------------|-----------------|
| `main.py` | CLI + orchestration of the 4 stages; CN timezone date helpers | `run(dry_run, local)` |
| `fetcher.py` | Multi-source fetch (RSS via `feedparser`, GitHub Trending via REST API), HTML cleaning, dedup by content hash | `fetch_all(cutoff_hours=72)` |
| `analyzer.py` | Local keyword prefilter → DeepSeek batch scoring → per-item deep analysis → daily intro | `analyze_all(items)` |
| `renderer.py` | Renders the dark-themed single-file HTML and a Markdown variant from the analysis dict | `render_html(data, date_str)`, `render_markdown(data, date_slug)` |
| `publisher.py` | Commits HTML/MD to the repo via GitHub Contents API, updates `docs/index.html` + `docs/archive.json`, opens a notification Issue | `publish(html, md, data, date_slug)` |

### The item dict (the contract between stages)
`fetcher` emits a list of dicts; later stages add keys. Preserve these keys when editing:
`id`, `source_id`, `source_name`, `category`, `priority`, `title`, `url`, `summary`,
`published_at` → analyzer adds `local_score`, `score`, `analysis`.

### analyzer.py cost optimization (important)
The analyzer is deliberately API-frugal (~15 DeepSeek calls/run, down from ~1345):
1. **Local rule prefilter** (zero API): keyword weights in `HIGH_VALUE_KW` / `LOW_VALUE_KW` +
   source-priority bonus in `HIGH_PRIORITY_SOURCES`, capped at 5 items per source, top 40 kept.
2. **Batch scoring**: 30 items per DeepSeek call, expecting a JSON array response.
3. **Deep analysis**: only the final `DEEP_N = 12` selected items (with per-category quota of 3).
4. **Daily summary**: one call.
`QUICK_N = 8` items become the "快讯" (quick-hits) list with no deep analysis.

When changing item counts, edit the `DEEP_N` / `QUICK_N` constants in `analyzer.py`.

## Running locally

```bash
pip install -r requirements.txt

export DEEPSEEK_API_KEY="sk-..."          # required for real analysis
export GITHUB_TOKEN="ghp_..."             # required only when publishing
export GITHUB_REPO="odysseusyes/AI-Daily-Newspaper"
export GITHUB_BRANCH="main"               # publish target (defaults to main)

python main.py --dry-run    # generate to ./output/ only, no GitHub writes (best for testing)
python main.py --local      # generate, save to ./output/, AND publish to GitHub
python main.py              # generate and publish to GitHub
```

`--dry-run` also writes a `{date}_data.json` to `output/` — useful for inspecting the
analysis structure. Individual modules are runnable for debugging:
`python fetcher.py` (prints first 3 fetched items), `python renderer.py` (writes a test HTML to `/tmp`).

## Environment variables

| Var | Used by | Notes |
|-----|---------|-------|
| `DEEPSEEK_API_KEY` | `analyzer.py` | DeepSeek API key. **There is a hard-coded fallback key in `analyzer.py` — do not rely on or commit real keys; prefer the env var / Actions secret.** |
| `GITHUB_TOKEN` | `publisher.py`, `fetcher.py` | Repo write access for publishing; also lifts GitHub API rate limits when fetching Trending. Provided automatically in Actions. |
| `GITHUB_REPO` | `publisher.py` | `owner/repo`. In Actions this is `${{ github.repository }}`. |
| `GITHUB_BRANCH` | `publisher.py` | Publish target branch, defaults to `main`. |

## CI / automation

`.github/workflows/daily.yml`:
- Trigger: `cron: "0 0 * * *"` (UTC 00:00 = 08:00 CST) + manual `workflow_dispatch` (with a `dry_run` boolean input).
- Runs `python main.py --local` (or `--dry-run --local` if dispatched with `dry_run=true`).
- Needs secret `DEEPSEEK_API_KEY`; `GITHUB_TOKEN` is auto-provided. Permissions: `contents: write`, `issues: write`.
- Uploads `output/` as an artifact (30-day retention) and opens a "build failed" Issue on failure.

`setup.sh` is a one-shot deploy helper (prompts for GitHub user/token, pushes, configures
Pages + the secret via the GitHub API, triggers the first run). It contains an embedded
DeepSeek key default — treat as untrusted/legacy.

## Output / generated files (do NOT hand-edit)

These are produced by the pipeline on every run — don't manually edit them, your changes will be overwritten:
- `docs/{YYYY-MM-DD}.html` — dated report page
- `docs/index.html` — copy of the latest report (the Pages homepage)
- `docs/archive.json` — rolling index, newest first, capped at 90 entries
- `reports/{YYYY-MM-DD}.md` — Markdown archive

Note: older `reports/AI日报_*.md` files exist from an earlier naming scheme; current runs use the `YYYY-MM-DD.md` slug.

## Conventions

- **Language**: code comments, log messages, and all generated content are in **Chinese**. Match this when editing.
- **Style**: section headers use box-drawing comment banners (`# ────`). Keep that visual style in existing files.
- **Timezone**: all user-facing dates are computed in **UTC+8 (Asia/Shanghai)** via `timezone(timedelta(hours=8))`. Never use naive local time.
- **Sources**: add/remove feeds by editing the `SOURCES` list in `fetcher.py`. Each needs `id`, `name`, `url`, `type` (`rss` or `github_api`), `category`, `priority`. New categories must also be added to `CATEGORY_CONFIG` in `renderer.py` and ideally `HIGH_PRIORITY_SOURCES` in `analyzer.py`.
- **Known inconsistency**: `SOURCES` currently holds 13 entries, but the README and `renderer.py` (`total_sources=12`) say "12 sources". If you change the source count, update the hard-coded `12` in `renderer.py` and the README too.
- **Resilience**: fetch/analyze code swallows per-source exceptions and logs warnings rather than crashing the run — preserve this fail-soft behavior. DeepSeek calls retry 3× with exponential backoff.

## Git workflow

- **Production branch is `main`** — the daily Action commits generated reports directly to `main`.
- Do feature/docs work on the designated dev branch, **not** `main`. The current dev branch for this task is `claude/claude-md-docs-YtNbL`.
- Don't open a PR unless explicitly asked.
- Avoid committing changes that would conflict with the bot's automated commits to `main` (i.e. don't hand-edit `docs/` or `reports/`).

## Sibling project

A related repo, **Skills-Daily-Newspaper**, lives alongside this one. It is a separate,
single-file GitHub-Trending digest focused on cross-border e-commerce / AI / automation —
do not confuse its conventions with this project's multi-module RSS pipeline.
