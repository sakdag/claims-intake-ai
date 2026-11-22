# MVP Terraform modules land in weekend 2 (M11).
# Placeholder keeps the deploy story visible from day one.

data "aws_caller_identity" "current" {}

output "account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "Verify this is the personal account before applying"
}

output "region" {
  value = var.aws_region
}
