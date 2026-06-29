# 音声AI日本語チューター デモのインフラ（Azure Container Apps、ハイブリッド構成）
# 重い音声処理は Azure Speech に同居させ、会話・採点(Bedrock)とメール(SES)は AWS を呼ぶ。

locals {
  name = "${var.project}-${var.environment}"

  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# Container Apps Environment のログ送信先
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# Container Apps の実行環境
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# コンテナイメージ置き場（名前は英数字のみ、かつグローバルで一意。重複したら変更すること）
resource "azurerm_container_registry" "main" {
  name                = "acr${replace(local.name, "-", "")}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false # 管理者資格情報は使わず、マネージドID で pull する
  tags                = local.tags
}

# Container App が ACR から pull するためのユーザー割り当てマネージドID
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# 発音採点・STT・TTS 用の Azure AI Speech
resource "azurerm_cognitive_account" "speech" {
  name                = "spe-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  kind                = "SpeechServices"
  sku_name            = "S0" # 無料枠を使うなら "F0"（サブスクに1つ、制限あり）
  tags                = local.tags
}

# PostgreSQL（デモ用）
# 注意: Flexible Server はゼロスケールしない。idle コストを無くしたい場合は、
# この3リソースを外し、下の Container App の "database-url" secret に
# 外部（例: Neon 無料枠）の接続文字列を入れる。
resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  administrator_login           = var.pg_admin_login
  administrator_password        = var.pg_admin_password
  sku_name                      = "B_Standard_B1ms" # 最小の Burstable
  storage_mb                    = 32768
  public_network_access_enabled = true
  zone                          = "1"
  tags                          = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "tutor"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

# デモ用: Azure サービスからのアクセスを許可（本番では送信元を絞ること）
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# バックエンド(API + ビルド済みSPA)を載せる Container App
resource "azurerm_container_app" "app" {
  name                         = "ca-${local.name}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  # 秘密情報はすべて secret に置き、env からは secret_name で参照する
  secret {
    name  = "azure-speech-key"
    value = azurerm_cognitive_account.speech.primary_access_key
  }
  secret {
    name  = "aws-access-key-id"
    value = var.aws_access_key_id
  }
  secret {
    name  = "aws-secret-access-key"
    value = var.aws_secret_access_key
  }
  secret {
    name  = "database-url"
    value = "postgresql://${var.pg_admin_login}:${var.pg_admin_password}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.main.name}?sslmode=require"
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 0 # ゼロスケール（商談時だけ起動）
    max_replicas = 2

    http_scale_rule {
      name                = "http"
      concurrent_requests = 20
    }

    container {
      name   = "api"
      image  = var.container_image # 初回はプレースホルダ。ビルド後 ACR の本番イメージに更新
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_SPEECH_REGION"
        value = azurerm_cognitive_account.speech.location
      }
      env {
        name        = "AZURE_SPEECH_KEY"
        secret_name = "azure-speech-key"
      }
      env {
        name  = "AWS_REGION"
        value = var.aws_region
      }
      env {
        name        = "AWS_ACCESS_KEY_ID"
        secret_name = "aws-access-key-id"
      }
      env {
        name        = "AWS_SECRET_ACCESS_KEY"
        secret_name = "aws-secret-access-key"
      }
      env {
        name  = "BEDROCK_MODEL_ID"
        value = var.bedrock_model_id
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "EMAIL_SENDER"
        value = var.email_sender
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/healthz"
        port      = 8000
      }
      readiness_probe {
        transport = "HTTP"
        path      = "/healthz"
        port      = 8000
      }
    }
  }

  # イメージは az containerapp update / CI で更新するので、Terraform では差分を無視
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }

  tags = local.tags
}
