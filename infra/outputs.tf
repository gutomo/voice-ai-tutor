output "app_url" {
  description = "デモの公開URL（ライブデモで開くアドレス）"
  value       = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "本番イメージの push 先"
  value       = azurerm_container_registry.main.login_server
}

output "speech_region" {
  description = "アプリの AZURE_SPEECH_REGION に対応"
  value       = azurerm_cognitive_account.speech.location
}

output "postgres_fqdn" {
  description = "PostgreSQL の接続先ホスト"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}
