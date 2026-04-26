"""
auto_start.py
=============
1. cloudflared tunnel を起動し、trycloudflare.com の動的URLを取得
2. LINE Messaging API の Webhook URL を自動更新
3. main.py (uvicorn) を起動

使い方: python auto_start.py
"""

import os
import re
import subprocess
import sys
import time
import threading
import httpx
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# ── 定数 ──────────────────────────────────────────────────────────────────────
CLOUDFLARED_CMD = ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"]
LINE_WEBHOOK_API = "https://api.line.me/v2/bot/channel/webhook/endpoint"
TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
TIMEOUT_SECONDS = 30  # URL抽出を待つ最大秒数


def update_line_webhook(tunnel_url: str) -> bool:
    """LINE Messaging API の Webhook URL を更新する。"""
    webhook_url = f"{tunnel_url}/callback"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"webhook": webhook_url}

    resp = httpx.put(LINE_WEBHOOK_API, headers=headers, json=payload, timeout=10)

    if resp.status_code == 200:
        print(f"[OK] LINE Webhook URL を更新しました: {webhook_url}")
        return True
    else:
        print(f"[ERROR] LINE Webhook 更新失敗: {resp.status_code} {resp.text}")
        return False


def start_cloudflared() -> tuple[subprocess.Popen, str]:
    """
    cloudflared を起動し、ログから trycloudflare.com の URL を抽出して返す。
    Returns: (process, tunnel_url)
    """
    print("[INFO] cloudflared を起動中...")

    proc = subprocess.Popen(
        CLOUDFLARED_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    tunnel_url = None
    deadline = time.time() + TIMEOUT_SECONDS
    collected_lines = []

    # バックグラウンドでログをファイルにも流すスレッド
    log_buffer = []

    def read_output():
        for line in proc.stdout:
            log_buffer.append(line)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    # URLが見つかるまでポーリング
    while time.time() < deadline:
        for line in log_buffer:
            if line not in collected_lines:
                collected_lines.append(line)
                print(f"[cloudflared] {line}", end="")
                match = TUNNEL_URL_PATTERN.search(line)
                if match:
                    tunnel_url = match.group()
                    return proc, tunnel_url
        time.sleep(0.3)

    raise TimeoutError(
        f"cloudflared からトンネルURLを {TIMEOUT_SECONDS}秒以内に取得できませんでした。"
    )


def start_server():
    """uvicorn で main.py を起動する（フォアグラウンド）。"""
    print("[INFO] uvicorn (main:app) を起動します...")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        check=False,
    )


def main():
    # 環境変数チェック
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[ERROR] .env に LINE_CHANNEL_ACCESS_TOKEN が設定されていません。")
        sys.exit(1)

    # 1. cloudflared 起動 & URL取得
    try:
        cf_proc, tunnel_url = start_cloudflared()
    except TimeoutError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"\n[INFO] トンネルURL取得: {tunnel_url}\n")

    # 2. LINE Webhook URL 更新
    if not update_line_webhook(tunnel_url):
        print("[WARN] Webhook の更新に失敗しましたが、サーバーは起動します。")

    # 3. main.py (uvicorn) 起動
    try:
        start_server()
    finally:
        # サーバー終了時に cloudflared も終了
        print("\n[INFO] cloudflared を終了します...")
        cf_proc.terminate()
        cf_proc.wait()


if __name__ == "__main__":
    main()
