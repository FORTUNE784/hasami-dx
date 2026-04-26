"""Notionデータベースの実際のプロパティ名と型を確認するスクリプト"""
from notion_client import Client
from config import settings

notion = Client(
    auth=settings.notion_api_key,
    notion_version="2022-06-28",
)

db = notion.databases.retrieve(settings.notion_database_id)

print("=== Notionデータベースのプロパティ一覧 ===")
for name, prop in db["properties"].items():
    print(f"  「{name}」: {prop['type']}")
