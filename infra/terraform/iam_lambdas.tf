# Per-function IAM roles (least privilege). ProcessClaim can invoke Bedrock but
# cannot send email or resume the workflow; SendEmail cannot invoke Bedrock.

locals {
  bedrock_resources = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/*",
    "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:application-inference-profile/*",
  ]
  ses_identity_arns = [
    aws_ses_email_identity.from.arn,
    aws_ses_email_identity.to.arn,
  ]
}

data "aws_iam_policy_document" "logs_only" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
  }
}

data "aws_iam_policy_document" "dynamo_rw" {
  statement {
    sid = "Dynamo"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.cases.arn,
      aws_dynamodb_table.audit.arn,
    ]
  }
}

data "aws_iam_policy_document" "s3_inbox_read" {
  statement {
    sid = "S3InboxRead"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.inbox.arn,
      "${aws_s3_bucket.inbox.arn}/*",
    ]
  }
}

data "aws_iam_policy_document" "s3_inbox_rw" {
  statement {
    sid = "S3InboxRW"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.inbox.arn,
      "${aws_s3_bucket.inbox.arn}/*",
    ]
  }
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid       = "Bedrock"
    actions   = ["bedrock:InvokeModel", "bedrock:Converse"]
    resources = local.bedrock_resources
  }
}

data "aws_iam_policy_document" "ses_send" {
  statement {
    sid       = "SesSend"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = local.ses_identity_arns
  }
}

data "aws_iam_policy_document" "sfn_callbacks" {
  statement {
    sid = "SfnTaskCallbacks"
    actions = [
      "states:SendTaskSuccess",
      "states:SendTaskFailure",
    ]
    resources = [aws_sfn_state_machine.claim_intake.arn]
  }
}

data "aws_iam_policy_document" "hmac_secret_read" {
  statement {
    sid       = "HmacSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.approval_hmac.arn]
  }
}

# --- ingest: S3 read + Dynamo ---
resource "aws_iam_role" "lambda_ingest" {
  name               = "${local.name_prefix}-lambda-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_ingest" {
  name = "${local.name_prefix}-lambda-ingest"
  role = aws_iam_role.lambda_ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.s3_inbox_read.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
    )
  })
}

# --- process: S3 read + Dynamo + Bedrock (untrusted text path; no SES / SFN) ---
resource "aws_iam_role" "lambda_process" {
  name               = "${local.name_prefix}-lambda-process"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_process" {
  name = "${local.name_prefix}-lambda-process"
  role = aws_iam_role.lambda_process.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.s3_inbox_read.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
      jsondecode(data.aws_iam_policy_document.bedrock_invoke.json).Statement,
    )
  })
}

# --- wait_review: Dynamo only ---
resource "aws_iam_role" "lambda_wait" {
  name               = "${local.name_prefix}-lambda-wait"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_wait" {
  name = "${local.name_prefix}-lambda-wait"
  role = aws_iam_role.lambda_wait.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
    )
  })
}

# --- send_email: Dynamo + SES + HMAC secret (no Bedrock) ---
resource "aws_iam_role" "lambda_send" {
  name               = "${local.name_prefix}-lambda-send"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_send" {
  name = "${local.name_prefix}-lambda-send"
  role = aws_iam_role.lambda_send.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
      jsondecode(data.aws_iam_policy_document.ses_send.json).Statement,
      jsondecode(data.aws_iam_policy_document.hmac_secret_read.json).Statement,
    )
  })
}

# --- finalize: Dynamo only ---
resource "aws_iam_role" "lambda_finalize" {
  name               = "${local.name_prefix}-lambda-finalize"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_finalize" {
  name = "${local.name_prefix}-lambda-finalize"
  role = aws_iam_role.lambda_finalize.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
    )
  })
}

# --- API: Dynamo + SFN callbacks + HMAC secret ---
resource "aws_iam_role" "lambda_api" {
  name               = "${local.name_prefix}-lambda-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_api" {
  name = "${local.name_prefix}-lambda-api"
  role = aws_iam_role.lambda_api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.dynamo_rw.json).Statement,
      jsondecode(data.aws_iam_policy_document.sfn_callbacks.json).Statement,
      jsondecode(data.aws_iam_policy_document.hmac_secret_read.json).Statement,
    )
  })
}

# --- email_ingest (optional): S3 RW ---
resource "aws_iam_role" "lambda_email_ingest" {
  count              = var.enable_inbound_email ? 1 : 0
  name               = "${local.name_prefix}-lambda-email-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda_email_ingest" {
  count = var.enable_inbound_email ? 1 : 0
  name  = "${local.name_prefix}-lambda-email-ingest"
  role  = aws_iam_role.lambda_email_ingest[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      jsondecode(data.aws_iam_policy_document.logs_only.json).Statement,
      jsondecode(data.aws_iam_policy_document.s3_inbox_rw.json).Statement,
    )
  })
}
