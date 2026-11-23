# Generate secrets in AWS instead of committing them as Terraform variables.

resource "random_password" "approval_hmac" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "approval_hmac" {
  name_prefix             = "${local.name_prefix}-approval-hmac-"
  description             = "HMAC secret for outbound approval tokens"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "approval_hmac" {
  secret_id     = aws_secretsmanager_secret.approval_hmac.id
  secret_string = random_password.approval_hmac.result
}

resource "random_password" "adjuster" {
  length           = 24
  special          = true
  override_special = "!@#%^&*-_"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

output "adjuster_password" {
  description = "Generated Cognito adjuster password (sensitive; retrieve via terraform output)"
  value       = var.enable_hosted_api ? random_password.adjuster.result : null
  sensitive   = true
}

output "approval_hmac_secret_arn" {
  value = aws_secretsmanager_secret.approval_hmac.arn
}
