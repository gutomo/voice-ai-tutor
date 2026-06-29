variable "project" {
  type        = string
  description = "リソース名のプレフィックス"
  default     = "jp-tutor"
}

variable "environment" {
  type        = string
  description = "環境名（demo など）"
  default     = "demo"
}

variable "location" {
  type        = string
  description = "Azureリージョン。ja-JPの発音採点・TTSに近い japaneast を既定にする"
  default     = "japaneast"
}

# 初回 apply 時のプレースホルダ。ビルド後に ACR の本番イメージへ置き換える。
variable "container_image" {
  type        = string
  description = "Container App が起動するイメージ"
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}

# ---- AWS（Bedrock + SES）。Azure側にリソースが無いので外から渡す ----

variable "aws_region" {
  type        = string
  description = "Bedrock の Claude が使えるリージョン"
  default     = "us-east-1"
}

variable "aws_access_key_id" {
  type        = string
  description = "Bedrock と SES を許可する IAM アクセスキー"
  sensitive   = true
}

variable "aws_secret_access_key" {
  type        = string
  description = "上記キーのシークレット"
  sensitive   = true
}

variable "bedrock_model_id" {
  type        = string
  description = "Bedrock のモデル/推論プロファイルID。Bedrockコンソールで確認して設定する（環境により異なるため既定値は置かない）"
}

variable "email_sender" {
  type        = string
  description = "SES で検証済みの送信元アドレス"
}

# ---- PostgreSQL ----

variable "pg_admin_login" {
  type        = string
  description = "PostgreSQL 管理者ユーザー名"
  default     = "tutoradmin"
}

variable "pg_admin_password" {
  type        = string
  description = "PostgreSQL 管理者パスワード"
  sensitive   = true
}
