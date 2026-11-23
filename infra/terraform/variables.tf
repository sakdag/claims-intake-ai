variable "aws_region" {
  type        = string
  description = "EU region for customer-account deploy"
  default     = "eu-north-1"
}

variable "aws_profile" {
  type        = string
  description = "Local AWS CLI profile — must be personal, never employer"
  default     = "personal"
}

variable "environment" {
  type    = string
  default = "demo"
}

variable "project_name" {
  type    = string
  default = "claims-intake-ai"
}

variable "allowed_account_id" {
  type        = string
  description = "Hard guard — refuse apply outside the deployment account"
  default     = "000000000000"
}

variable "model_id" {
  type        = string
  description = "Bedrock model / inference profile id"
  default     = "eu.amazon.nova-micro-v1:0"
}

variable "approval_hmac_secret" {
  type        = string
  description = "HMAC secret for signed outbound approvals (set via tfvars, never commit)"
  sensitive   = true
  default     = "demo-change-me"
}

variable "ses_from_email" {
  type        = string
  description = "Verified SES From address for missing-doc emails"
  default     = "you@example.com"
}

variable "ses_to_email" {
  type        = string
  description = "Verified SES To address (sandbox requires verified recipient)"
  default     = "you@example.com"
}

variable "operator_iam_user" {
  type        = string
  description = "IAM user that can still run the local FastAPI review UI (SendTaskSuccess)"
  default     = "claims-intake-admin"
}

variable "enable_hosted_api" {
  type        = bool
  description = "Deploy Cognito + API Gateway HTTP API + review API Lambda"
  default     = true
}

variable "cors_origins" {
  type        = list(string)
  description = "Browser origins allowed to call the hosted API"
  default     = ["http://localhost:5173", "http://127.0.0.1:5173"]
}

variable "adjuster_username" {
  type        = string
  description = "Cognito username for the demo adjuster"
  default     = "adjuster"
}

variable "adjuster_password" {
  type        = string
  description = "Initial Cognito password (tfvars only; change after first login if desired)"
  sensitive   = true
  default     = "replace-with-strong-password"
}

variable "adjuster_email" {
  type        = string
  description = "Email attribute on the Cognito adjuster user"
  default     = "you@example.com"
}
