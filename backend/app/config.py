"""アプリ設定。秘密情報は .env から読み込む（Phase 0 ではすべて任意）。

外部API（Azure / Bedrock / SES）の値が未設定でもアプリは起動する。
各 Phase で必要になった時点で必須化していく。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure AI Speech (STT / 発音評価 / TTS)
    azure_speech_key: str | None = None
    azure_speech_region: str | None = None

    # AWS (Bedrock Claude + SES)
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    bedrock_model_id: str | None = None

    # データベース
    database_url: str = "postgresql://tutor:tutor@localhost:5432/tutor"

    # メール送信元 (SES で検証済みのアドレス)
    email_sender: str | None = None


settings = Settings()
