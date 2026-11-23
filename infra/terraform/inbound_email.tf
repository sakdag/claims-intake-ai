# Inbound email → S3 email-raw/ → EmailIngest Lambda → inbox/*.json → existing Starter.
# Off by default. SES *receiving* is not available in every region (not in eu-north-1);
# set ses_inbound_region to a receiving-capable region (e.g. eu-west-1) and point MX there.

provider "aws" {
  alias   = "ses_inbound"
  region  = var.ses_inbound_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = var.project_name
      Customer    = "elm-and-stone"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

resource "aws_cloudwatch_log_group" "email_ingest" {
  count             = var.enable_inbound_email ? 1 : 0
  name              = "/aws/lambda/${local.name_prefix}-email-ingest"
  retention_in_days = 14
}

resource "aws_lambda_function" "email_ingest" {
  count            = var.enable_inbound_email ? 1 : 0
  function_name    = "${local.name_prefix}-email-ingest"
  role             = aws_iam_role.lambda_email_ingest[0].arn
  handler          = "claims_intake.aws_handlers.email_ingest.handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 512
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = {
      INBOX_PREFIX = "inbox/"
    }
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda_email_ingest,
    aws_cloudwatch_log_group.email_ingest,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_permission" "email_ingest_s3" {
  count         = var.enable_inbound_email ? 1 : 0
  statement_id  = "AllowS3InvokeEmailIngest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.email_ingest[0].function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.inbox.arn
}

# Extend inbox notifications: email-raw/ → email_ingest, inbox/*.json → starter
resource "aws_s3_bucket_notification" "inbox_with_email" {
  count  = var.enable_inbound_email ? 1 : 0
  bucket = aws_s3_bucket.inbox.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.starter.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "inbox/"
    filter_suffix       = ".json"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.email_ingest[0].arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "email-raw/"
  }

  depends_on = [
    aws_lambda_permission.allow_s3,
    aws_lambda_permission.email_ingest_s3,
  ]
}

# When inbound email is off, keep the original JSON-only notification from main.tf.
# When on, main.tf notification must not conflict — see lifecycle note below.

resource "aws_ses_domain_identity" "inbound" {
  count    = var.enable_inbound_email ? 1 : 0
  provider = aws.ses_inbound
  domain   = var.inbound_email_domain
}

resource "aws_ses_receipt_rule_set" "inbound" {
  count         = var.enable_inbound_email ? 1 : 0
  provider      = aws.ses_inbound
  rule_set_name = "${local.name_prefix}-inbound"
}

resource "aws_ses_active_receipt_rule_set" "inbound" {
  count         = var.enable_inbound_email ? 1 : 0
  provider      = aws.ses_inbound
  rule_set_name = aws_ses_receipt_rule_set.inbound[0].rule_set_name
}

data "aws_iam_policy_document" "inbox_ses_put" {
  count = var.enable_inbound_email ? 1 : 0
  statement {
    sid       = "AllowSESPuts"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.inbox.arn}/email-raw/*"]
    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_s3_bucket_policy" "inbox_ses" {
  count  = var.enable_inbound_email ? 1 : 0
  bucket = aws_s3_bucket.inbox.id
  policy = data.aws_iam_policy_document.inbox_ses_put[0].json
}

resource "aws_ses_receipt_rule" "store_raw" {
  count         = var.enable_inbound_email ? 1 : 0
  provider      = aws.ses_inbound
  name          = "${local.name_prefix}-store-raw"
  rule_set_name = aws_ses_receipt_rule_set.inbound[0].rule_set_name
  recipients    = [var.inbound_email_address]
  enabled       = true
  scan_enabled  = true

  s3_action {
    bucket_name       = aws_s3_bucket.inbox.bucket
    object_key_prefix = "email-raw/"
    position          = 1
  }

  depends_on = [aws_s3_bucket_policy.inbox_ses]
}

output "inbound_email_enabled" {
  value = var.enable_inbound_email
}

output "inbound_email_address" {
  value = var.enable_inbound_email ? var.inbound_email_address : null
}

output "inbound_email_setup_note" {
  value = var.enable_inbound_email ? join("\n", [
    "1. Verify domain ${var.inbound_email_domain} DNS (SES identity in ${var.ses_inbound_region}).",
    "2. Add MX for ${var.inbound_email_domain} → inbound-smtp.${var.ses_inbound_region}.amazonaws.com",
    "3. Mail to ${var.inbound_email_address} lands in s3://…/email-raw/ then EmailIngest writes inbox/*.json.",
  ]) : "Set enable_inbound_email=true (and a real domain) when ready. SES receiving is not available in eu-north-1; default inbound region is eu-west-1."
}
