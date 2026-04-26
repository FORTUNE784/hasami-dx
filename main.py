import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

import google.generativeai as genai
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent

from config import settings
from notion_schema import create_notion_page

# ── ロギング ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Gemini 初期化 ─────────────────────────────────────────────────────────────
genai.configure(api_key=settings.gemini_api_key)

# 利用可能なモデル一覧をログ出力（404 デバッグ用・確認後に削除可）
try:
    available_models = [
        m.name for m in genai.list_models()
        if "generateContent" in m.supported_generation_methods
    ]
    logger.info("利用可能な Gemini モデル一覧: %s", available_models)
except Exception as _e:
    logger.warning("モデル一覧の取得に失敗しました: %s", _e)

SYSTEM_PROMPT = """
お前は長崎県波佐見町の窯元で30年働く、ベテラン事務員だ。
FAXの掠れや手書きの癖字、専門用語（呉須、網目、十草、青磁、白磁、素焼、本焼など）を完璧に理解し、
文脈から正しい文字を推測せよ。
もし数字が読み取りにくい場合は、前後の単価と合計金額の計算整合性から推論して補完すること。

以下のJSONスキーマに従って伝票の内容を抽出し、必ずJSONのみを返せ。余計な説明は不要。

{
  "sender": "送信元の会社名または個人名。不明なら '不明'",
  "sending_date": "送信日。YYYY-MM-DD形式。不明なら null",
  "delivery_date": "納期。YYYY-MM-DD形式。不明なら null",
  "total_amount": "合計金額の数値（円）。不明なら null",
  "items": [
    {
      "product_name": "品名（例: 白磁湯呑、呉須網目皿 など）",
      "quantity": "数量（整数）。不明なら null",
      "unit_price": "単価（円、整数）。不明なら null"
    }
  ],
  "ai_notes": "読み取りの不確かな箇所、推論の根拠、特記事項などを記載。問題なければ空文字"
}
""".strip()

gemini_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_PROMPT,
)

# ── LINE SDK 初期化 ───────────────────────────────────────────────────────────
line_config = Configuration(access_token=settings.line_channel_access_token)
handler = WebhookHandler(settings.line_channel_secret)

# ── BackgroundTasks をハンドラーに橋渡しするためのコンテキスト変数 ─────────────
_bg_tasks: ContextVar[BackgroundTasks] = ContextVar("_bg_tasks")


# ── FastAPI ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("波佐見焼FAX読み取りBot 起動完了")
    yield
    logger.info("Bot シャットダウン")


app = FastAPI(title="波佐見焼 FAX読み取りBot", lifespan=lifespan)


# ── ヘルパー関数 ──────────────────────────────────────────────────────────────

def _extract_from_gemini(image_bytes: bytes) -> dict:
    """画像バイナリをGeminiに渡してJSONを抽出する。"""
    image_part = {"mime_type": "image/jpeg", "data": image_bytes}

    response = gemini_model.generate_content(
        contents=[image_part, "この伝票を解析してください。"],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()
    logger.info("Gemini raw response: %s", raw[:300])

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Geminiの応答をJSONとして解析できませんでした: {raw[:200]}")


def _build_reply_text(extracted: dict) -> str:
    """Notionへの登録完了メッセージを生成する。"""
    sender = extracted.get("sender") or "不明"
    total = extracted.get("total_amount")
    delivery = extracted.get("delivery_date")
    items = extracted.get("items") or []
    ai_notes = extracted.get("ai_notes") or ""

    amount_str = f"¥{int(total):,}" if total else "不明"
    delivery_str = delivery if delivery else "記載なし"

    item_lines = "\n".join(
        [f"  ・{it.get('product_name', '?')} ×{it.get('quantity', '?')}"
         + (f" (@¥{int(it['unit_price']):,})" if it.get("unit_price") else "")
         for it in items[:10]]
    )

    lines = [
        "✅ Notionへの登録が完了しました！",
        "",
        f"📤 送信元: {sender}",
        f"💰 合計金額: {amount_str}",
        f"📦 納期: {delivery_str}",
    ]

    if item_lines:
        lines += ["", "📋 品目:", item_lines]

    if ai_notes:
        lines += ["", f"⚠️ AI備考: {ai_notes[:100]}"]

    return "\n".join(lines)


# ── Webhook エンドポイント ────────────────────────────────────────────────────

@app.post("/webhook")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(..., alias="X-Line-Signature"),
):
    body = await request.body()
    body_text = body.decode("utf-8")

    # handle_image が background_tasks を参照できるようコンテキスト変数にセット
    _bg_tasks.set(background_tasks)

    try:
        handler.handle(body_text, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return {"status": "ok"}


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent):
    """画像メッセージを受信したら、バックグラウンド処理を予約するだけ。"""
    logger.info("画像メッセージ受信: message_id=%s — バックグラウンド処理を予約", event.message.id)
    bg = _bg_tasks.get()
    bg.add_task(_process_image_event, event)


async def _process_image_event(event: MessageEvent):
    """Gemini解析 → Notion登録 → LINEリプライ（バックグラウンドで実行）。"""
    reply_token = event.reply_token
    message_id = event.message.id

    async with AsyncApiClient(line_config) as api_client:
        line_api = AsyncMessagingApi(api_client)

        try:
            # 1. LINEから画像バイナリを取得（BlobクライアントはMessagingApiとは別）
            logger.info("画像取得中: message_id=%s", message_id)
            blob_api = AsyncMessagingApiBlob(api_client)
            image_bytes = await blob_api.get_message_content(message_id)

            # 2. Geminiで解析
            logger.info("Gemini解析中...")
            extracted = _extract_from_gemini(image_bytes)
            logger.info("抽出結果: %s", extracted)

            # 3. Notionへ登録（image_url は LINE画像のため外部公開不可 → None）
            logger.info("Notion登録中...")
            await create_notion_page(extracted, image_url=None)
            logger.info("Notion登録完了")

            # 4. 完了リプライ
            reply_text = _build_reply_text(extracted)

        except Exception as e:
            logger.exception("処理中にエラーが発生しました")
            reply_text = (
                "⛔ 伝票の読み取り中にエラーが発生しました。\n"
                f"詳細: {str(e)[:100]}\n"
                "画像を再送するか、担当者に連絡してください。"
            )

        await line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


# ── 起動 ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
