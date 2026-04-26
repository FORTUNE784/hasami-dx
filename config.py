import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LINE Messaging API
    line_channel_secret: str
    line_channel_access_token: str

    # Google Gemini
    gemini_api_key: str

    # Notion
    notion_api_key: str
    notion_database_id: str = "34372f4596c680b6a962c19772e5a4b0"

    # 読み込み設定の強化
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # 定義外の変数が .env にあっても無視する
    )

# インスタンス化してエクスポート
settings = Settings()
