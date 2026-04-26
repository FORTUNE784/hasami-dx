from notion_client import Client
from config import settings

notion = Client(
    auth=settings.notion_api_key,
    notion_version="2022-06-28",
)

def _rt(text: str) -> dict:
    return {"rich_text": [{"text": {"content": str(text)[:2000]}}]}

async def create_notion_page(extracted: dict, image_url: str | None = None):
    items = extracted.get("items") or []
    product_names = "\n".join([it.get("product_name") or "?" for it in items])
    quantities    = "\n".join([str(it.get("quantity") or "?") for it in items])
    unit_prices   = "\n".join([str(it.get("unit_price") or "?") for it in items])

    properties = {
        "日付":  _rt(extracted.get("sending_date") or ""),
        "宛先":  _rt(extracted.get("sender") or ""),
        "品名":  _rt(product_names),
        "数量":  _rt(quantities),
        "単価":  _rt(unit_prices),
    }

    return notion.pages.create(
        parent={"database_id": settings.notion_database_id},
        properties=properties,
    )
