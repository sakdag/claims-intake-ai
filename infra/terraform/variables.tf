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
