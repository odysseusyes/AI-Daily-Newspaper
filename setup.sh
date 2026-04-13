#!/bin/bash
# ═══════════════════════════════════════════════════════
#  AI 前沿日报 · 一键部署脚本
#  运行前请确保已安装 git，并已登录 GitHub
# ═══════════════════════════════════════════════════════

set -e

# ── 颜色输出 ──────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}✅ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo ""
echo "═══════════════════════════════════════"
echo "   🤖  AI 前沿日报 · 一键部署"
echo "═══════════════════════════════════════"
echo ""

# ── 0. 检测脚本所在目录 ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "项目目录: $SCRIPT_DIR"

# ── 1. 获取 GitHub 信息 ──────────────────────────────
echo ""
read -p "📌 请输入你的 GitHub 用户名: " GH_USER
read -p "📌 请输入仓库名 [默认: AI-Daily-Newspaper]: " GH_REPO
GH_REPO=${GH_REPO:-AI-Daily-Newspaper}
read -s -p "🔑 请输入 GitHub Personal Access Token (ghp_xxx): " GH_TOKEN
echo ""
read -p "🔑 DeepSeek API Key [默认已内置]: " DS_KEY
DS_KEY=${DS_KEY:-sk-486e1846d4e140b486cf9bfad64c9dd2}

REMOTE_URL="https://${GH_TOKEN}@github.com/${GH_USER}/${GH_REPO}.git"

# ── 2. 初始化 git ─────────────────────────────────────
cd "$SCRIPT_DIR"

if [ ! -d ".git" ]; then
  info "初始化 git 仓库..."
  git init
  git branch -M main
fi

# 配置 git 用户
git config user.email "ai-daily@auto.bot" 2>/dev/null || true
git config user.name "AI Daily Bot" 2>/dev/null || true

# ── 3. 创建必要目录和占位文件 ─────────────────────────
mkdir -p docs reports

# 创建占位 index.html（部署前的等待页）
if [ ! -f "docs/index.html" ]; then
cat > docs/index.html << 'EOF'
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>AI 日报 · 初始化中</title>
<style>body{background:#0f172a;color:#e2e8f0;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;text-align:center;}h1{font-size:2rem;}p{color:#94a3b8;}</style>
</head>
<body><div><h1>🤖 AI 前沿日报</h1><p>正在初始化，第一期日报将于今天 08:00 自动生成</p></div></body>
</html>
EOF
fi

# 创建占位 archive.json
if [ ! -f "docs/archive.json" ]; then
  echo "[]" > docs/archive.json
fi

# ── 4. 添加并提交所有文件 ─────────────────────────────
info "提交代码..."
git add .
git diff --cached --quiet || git commit -m "🚀 初始化 AI 前沿日报项目"

# ── 5. 设置远端并推送 ─────────────────────────────────
info "推送到 GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"
git push -u origin main --force

log "代码推送成功！"

# ── 6. 通过 API 配置 GitHub Pages ─────────────────────
info "配置 GitHub Pages (docs 目录)..."
curl -s -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/pages" \
  -d '{"source":{"branch":"main","path":"/docs"}}' > /dev/null 2>&1 || true

# 如果已存在则更新
curl -s -X PUT \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/pages" \
  -d '{"source":{"branch":"main","path":"/docs"}}' > /dev/null 2>&1 || true

log "GitHub Pages 配置完成"

# ── 7. 设置 DEEPSEEK_API_KEY Secret ──────────────────
info "设置 DEEPSEEK_API_KEY Secret..."

# 获取仓库公钥（用于加密 secret）
PUBKEY_RESP=$(curl -s \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/actions/secrets/public-key")

KEY_ID=$(echo "$PUBKEY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('key_id',''))" 2>/dev/null)
PUB_KEY=$(echo "$PUBKEY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('key',''))" 2>/dev/null)

if [ -n "$KEY_ID" ] && [ -n "$PUB_KEY" ]; then
  # 用 Python 加密 secret（需要 PyNaCl）
  pip install PyNaCl --quiet --break-system-packages 2>/dev/null || pip install PyNaCl --quiet 2>/dev/null || true

  ENCRYPTED=$(python3 - <<PYEOF
import base64, sys
try:
    from nacl import encoding, public
    pub_key = public.PublicKey(base64.b64decode("$PUB_KEY"))
    box = public.SealedBox(pub_key)
    encrypted = box.encrypt(b"$DS_KEY")
    print(base64.b64encode(encrypted).decode())
except Exception as e:
    print("ERROR: " + str(e), file=sys.stderr)
    sys.exit(1)
PYEOF
  )

  if [ -n "$ENCRYPTED" ]; then
    curl -s -X PUT \
      -H "Authorization: Bearer $GH_TOKEN" \
      -H "Accept: application/vnd.github.v3+json" \
      "https://api.github.com/repos/${GH_USER}/${GH_REPO}/actions/secrets/DEEPSEEK_API_KEY" \
      -d "{\"encrypted_value\":\"$ENCRYPTED\",\"key_id\":\"$KEY_ID\"}" > /dev/null

    log "DEEPSEEK_API_KEY Secret 设置成功"
  else
    warn "Secret 加密失败，请手动设置（见下方说明）"
  fi
else
  warn "无法获取仓库公钥，请手动设置 Secret"
fi

# ── 8. 触发首次运行 ───────────────────────────────────
info "触发首次工作流运行..."
curl -s -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/actions/workflows/daily.yml/dispatches" \
  -d '{"ref":"main"}' > /dev/null 2>&1 || warn "首次触发失败，请在 Actions 页面手动运行"

# ── 完成 ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  ✅ 部署完成！"
echo ""
echo "  🌐 日报地址: https://${GH_USER}.github.io/${GH_REPO}/"
echo "  📌 仓库地址: https://github.com/${GH_USER}/${GH_REPO}"
echo "  ⚙️  Actions:  https://github.com/${GH_USER}/${GH_REPO}/actions"
echo ""
echo "  📧 订阅方式: Watch 仓库 → Custom → Issues ✓"
echo "  ⏰ 自动运行: 每天北京时间 08:00"
echo "═══════════════════════════════════════"
echo ""
