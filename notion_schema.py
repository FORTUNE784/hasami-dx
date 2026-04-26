"""Notion 書き込みロジック

新スキーマ（固定構造 + 柔軟テキスト欄）:
  タイトル / 送信元 / 日付 / 品目 / 合計金額 / 備考 / 生データ / ステータス / 受信日時
"""

import json
import logging
from notion_client import Client
from config import settings

logger = logging.getLogger(__name__)
notion = Client(auth=settings.notion_api_key)


def _truncate(text: str, max_chars: int = 2000) -> str:
    """Notionのrich_textは2000文字制限"""
    if not text:
        return ""
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


async def create_notion_page(extracted: dict, image_url: str = None) -> dict:
    """抽出結果をNotionの新規ページとして登録する。"""
    sender = extracted.get("sender") or "不明"
    date = extracted.get("sending_date")
    items = extracted.get("items") or []
    total = extracted.get("total_amount")
    notes = extracted.get("ai_notes") or ""

    # タイトルは「送信元 - 日付」で自動生成
    title = f"{sender} - {date}" if date else sender

    # 品目リストを複数行テキストに整形
    item_lines = []
    for it in items:
        name = it.get("product_name", "?")
        qty = it.get("quantity", "?")
        price = it.get("unit_price")
        if price is not None:
            item_lines.append(f"・{name} {qty}個 @{price}円")
        else:
            item_lines.append(f"・{name} {qty}個")
    items_text = "\n".join(item_lines) or "(品目なし)"

    # 生データ（保険として全文保存）
    raw_json = json.dumps(extracted, ensure_ascii=False, indent=2)

    properties = {
        "タイトル": {"title": [{"text": {"content": _truncate(title, 200)}}]},
        "送信元": {"rich_text": [{"text": {"content": _truncate(sender)}}]},
        "品目": {"rich_text": [{"text": {"content": _truncate(items_text)}}]},
        "備考": {"rich_text": [{"text": {"content": _truncate(notes)}}]},
        "生データ": {"rich_text": [{"text": {"content": _truncate(raw_json)}}]},
        "ステータス": {"select": {"name": "未処理"}},
    }

    # 日付があれば追加
    if date:
        properties["日付"] = {"date": {"start": date}}

    # 合計金額があれば追加
    if total is not None:
        try:
            properties["合計金額"] = {"number": float(total)}
        except (TypeError, ValueError):
            logger.warning(f"合計金額の変換失敗: {total}")

    db_id = settings.NOTION_DATABASE_ID
    logger.info(f"Notion登録: db_id={db_id}, title={title}")

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
    )
    logger.info(f"Notion登録成功: page_id={page.get('id')}")
    return page


def build_summary(extracted: dict) -> str:
    """LINE返信用の要約テキスト"""
    sender = extracted.get("sender") or "不明"
    date = extracted.get("sending_date") or "日付不明"
    total = extracted.get("total_amount")
    items = extracted.get("items") or []

    item_lines = []
    for it in items[:5]:
        name = it.get("product_name", "?")
        qty = it.get("quantity", "?")
        item_lines.append(f"・{name} {qty}個")
    items_str = "\n".join(item_lines) if item_lines else "(品目なし)"
    if len(items) > 5:
        items_str += f"\n他{len(items) - 5}件"

    total_str = f"¥{total:,}" if total is not None else "金額不明"

    parts = [
        "✅ Notionに登録しました",
        f"📅 {date}　📤 {sender}",
        items_str,
        f"💰 {total_str}",
    ]

    notes = extracted.get("ai_notes")
    if notes:
        parts.append(f"⚠️ {notes[:100]}")

    return "\n".join(parts)
