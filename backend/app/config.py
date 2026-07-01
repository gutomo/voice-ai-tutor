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

    # アップロードした音声の保存先 (相対パスは backend/ 起点に解決する)
    upload_dir: str = "uploads"

    # 発音採点で「弱い」とみなす単語のしきい値 (Azure の Mispronunciation 判定=60 に合わせる)
    weak_word_threshold: float = 60.0

    # メール送信元 (SES で検証済みのアドレス)
    email_sender: str | None = None
    # 教師レポートの宛先 (未設定なら email_sender に送る＝サンドボックスでも届く)
    teacher_email: str | None = None
    # 学習者メールの「次回リンク」の基点 (フロントの公開URL)
    app_base_url: str = "http://localhost:5173"

    def azure_ready(self) -> bool:
        """Azure Speech の発音採点 / TTS に必要な鍵とリージョンが揃っているか。"""
        return bool(self.azure_speech_key and self.azure_speech_region)

    def bedrock_ready(self) -> bool:
        """Bedrock Claude の会話生成 / ルーブリック採点に必要な値が揃っているか。"""
        return bool(self.aws_access_key_id and self.aws_secret_access_key and self.bedrock_model_id)

    def ses_ready(self) -> bool:
        """SES の結果メール送信に必要な AWS 認証情報と送信元が揃っているか。"""
        return bool(self.aws_access_key_id and self.aws_secret_access_key and self.email_sender)


settings = Settings()
