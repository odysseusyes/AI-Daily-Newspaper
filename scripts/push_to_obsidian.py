#!/usr/bin/env python3
"""
推送日报到 Obsidian Vault
支持两种方式：
  1. Obsidian Local REST API（本地运行时）
  2. Git Push 到 Vault 仓库（GitHub Actions CI 时）
"""

import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ─────────────────────────────────────────────
# 方式 1：Obsidian Local REST API
# 需要安装插件：obsidian-local-rest-api
# ─────────────────────────────────────────────
def push_via_local_api(
    content: str,
    vault_folder: str,
    filename: str,
    api_key: str,
    base_url: str = "http://localhost:27123",
) -> bool:
    if not HAS_REQUESTS:
        print("⚠️  requests 未安装，跳过 Local REST API 方式")
        return False

    vault_path = f"{vault_folder}/{filename}"
    url = f"{base_url}/vault/{vault_path}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "text/markdown",
    }

    try:
        resp = requests.put(url, data=content.encode("utf-8"), headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            print(f"✅ [Local API] 已推送至 Obsidian：{vault_path}")
            return True
        else:
            print(f"❌ [Local API] 失败 {resp.status_code}：{resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ [Local API] 连接失败：{e}")
        return False


# ─────────────────────────────────────────────
# 方式 2：Git Push 到 Vault 仓库
# 适用于 GitHub Actions，Vault 用 git 同步（Obsidian Git 插件）
# ─────────────────────────────────────────────
def push_via_git(
    content: str,
    vault_folder: str,
    filename: str,
    vault_repo: str,   # 格式：https://TOKEN@github.com/user/vault.git
    date_str: str,
) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Clone Vault 仓库（浅克隆，速度快）
        print(f"📥 克隆 Vault 仓库...")
        result = subprocess.run(
            ["git", "clone", "--depth=1", vault_repo, str(tmp_path / "vault")],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"❌ Clone 失败：{result.stderr}")
            return False

        vault_dir = tmp_path / "vault"
        target_dir = vault_dir / vault_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        # 写入文件
        target_file = target_dir / filename
        target_file.write_text(content, encoding="utf-8")
        print(f"💾 写入文件：{vault_folder}/{filename}")

        # Git 配置
        subprocess.run(["git", "config", "user.email", "ai-daily@auto.bot"],
                       cwd=vault_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "AI Daily Bot"],
                       cwd=vault_dir, capture_output=True)

        # 提交推送
        subprocess.run(["git", "add", str(target_file)], cwd=vault_dir)
        commit_msg = f"📰 AI日报 {date_str} - 自动生成"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=vault_dir, capture_output=True, text=True
        )
        if "nothing to commit" in result.stdout:
            print("ℹ️  当日日报已存在，无变更")
            return True

        result = subprocess.run(
            ["git", "push"], cwd=vault_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ [Git] 已推送至 Vault 仓库：{vault_folder}/{filename}")
            return True
        else:
            print(f"❌ [Git] Push 失败：{result.stderr}")
            return False


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="推送日报到 Obsidian")
    parser.add_argument("--file",         required=True, help="本地日报文件路径")
    parser.add_argument("--vault-folder", default="AI日报", help="Vault 内目标文件夹")
    args = parser.parse_args()

    # 读取日报内容
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ 文件不存在：{args.file}")
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    filename = file_path.name
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 环境变量
    local_api_key  = os.environ.get("OBSIDIAN_API_KEY", "")
    vault_repo_url = os.environ.get("OBSIDIAN_VAULT_REPO", "")
    obsidian_token = os.environ.get("OBSIDIAN_TOKEN", "")

    # 如果有 vault repo，注入 token
    if vault_repo_url and obsidian_token:
        # 格式转换：https://github.com/... → https://TOKEN@github.com/...
        vault_repo_url = vault_repo_url.replace(
            "https://", f"https://{obsidian_token}@"
        )

    success = False

    # 优先尝试 Local REST API（本地环境）
    if local_api_key:
        success = push_via_local_api(
            content=content,
            vault_folder=args.vault_folder,
            filename=filename,
            api_key=local_api_key,
        )

    # 如果 Local API 失败或不可用，尝试 Git 推送（CI 环境）
    if not success and vault_repo_url:
        success = push_via_git(
            content=content,
            vault_folder=args.vault_folder,
            filename=filename,
            vault_repo=vault_repo_url,
            date_str=date_str,
        )

    # 最终 fallback：仅保留在 output 目录，供 artifact 下载
    if not success:
        print("⚠️  无法推送至 Obsidian，文件已保存在 output/ 目录")
        print("   → 手动下载 GitHub Actions Artifacts 后放入 Vault")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
