data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  account_ok  = data.aws_caller_identity.current.account_id == var.allowed_account_id
}

resource "null_resource" "account_guard" {
  lifecycle {
    precondition {
      condition     = local.account_ok
      error_message = "Refusing to deploy: account ${data.aws_caller_identity.current.account_id} != allowed ${var.allowed_account_id} (deployment only)."
    }
  }
}

# --- KMS ---
resource "aws_kms_key" "main" {
  description             = "${local.name_prefix} claims intake"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.main.key_id
}

# --- S3 inbox ---
resource "aws_s3_bucket" "inbox" {
  bucket_prefix = "${local.name_prefix}-inbox-"
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  rule {
    apply_server_side_encryption_by_default {
      # AES256 avoids CMK policy coupling for the demo teardown loop;
      # aws_kms_key.main remains for secrets / future envelope encryption.
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "inbox" {
  bucket                  = aws_s3_bucket.inbox.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- DynamoDB ---
resource "aws_dynamodb_table" "cases" {
  name         = "${local.name_prefix}-cases"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "audit" {
  name         = "${local.name_prefix}-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}

# --- Lambda package ---
resource "null_resource" "lambda_package" {
  triggers = {
    # Single hash drives both rebuild and Lambda source_code_hash updates
    code_hash = sha256(join("", [
      filesha256("${path.module}/../lambda/package.sh"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/ingest.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/process_claim.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/starter.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/wait_for_review.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/send_email.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/finalize.py"),
      filesha256("${path.module}/../../src/claims_intake/pipeline/ingest.py"),
      filesha256("${path.module}/../../src/claims_intake/llm/client.py"),
      filesha256("${path.module}/../stepfunctions/claim_intake.asl.json"),
    ]))
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/../lambda/package.sh"
  }
}

locals {
  lambda_zip = "${path.module}/../../build/claims_intake_lambda.zip"
}

# --- IAM ---
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
  }

  statement {
    sid = "S3Inbox"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.inbox.arn,
      "${aws_s3_bucket.inbox.arn}/*",
    ]
  }

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

  statement {
    sid = "Kms"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.main.arn]
  }

  statement {
    sid = "Bedrock"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:Converse",
    ]
    resources = ["*"]
  }

  statement {
    sid = "SesSend"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name_prefix}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.name_prefix}-ingest"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "process" {
  name              = "/aws/lambda/${local.name_prefix}-process"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "wait_review" {
  name              = "/aws/lambda/${local.name_prefix}-wait-review"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "send_email" {
  name              = "/aws/lambda/${local.name_prefix}-send-email"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "finalize" {
  name              = "/aws/lambda/${local.name_prefix}-finalize"
  retention_in_days = 14
}

locals {
  lambda_env = {
    CLAIMS_AWS_REGION           = var.aws_region
    CLAIMS_AWS_PROFILE          = ""
    CLAIMS_MODEL_PROVIDER       = "bedrock"
    CLAIMS_MODEL_ID             = var.model_id
    CASES_TABLE                 = aws_dynamodb_table.cases.name
    AUDIT_TABLE                 = aws_dynamodb_table.audit.name
    CLAIMS_APPROVAL_HMAC_SECRET = var.approval_hmac_secret
    SES_FROM_EMAIL              = var.ses_from_email
    SES_TO_EMAIL                = var.ses_to_email
  }
}

# --- SES identities (sandbox: verify from + to) ---
resource "aws_ses_email_identity" "from" {
  email = var.ses_from_email
}

resource "aws_ses_email_identity" "to" {
  email = var.ses_to_email
}

resource "aws_lambda_function" "ingest" {
  function_name = "${local.name_prefix}-ingest"
  role          = aws_iam_role.lambda.arn
  handler       = "claims_intake.aws_handlers.ingest.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 512
  filename      = local.lambda_zip
  # Use package trigger hash (not filebase64sha256) to avoid plan/apply
  # inconsistency when local-exec rewrites the zip in the same apply.
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.ingest,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "process" {
  function_name = "${local.name_prefix}-process"
  role          = aws_iam_role.lambda.arn
  handler       = "claims_intake.aws_handlers.process_claim.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 1024
  filename      = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.process,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "wait_review" {
  function_name    = "${local.name_prefix}-wait-review"
  role             = aws_iam_role.lambda.arn
  handler          = "claims_intake.aws_handlers.wait_for_review.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.wait_review,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "send_email" {
  function_name    = "${local.name_prefix}-send-email"
  role             = aws_iam_role.lambda.arn
  handler          = "claims_intake.aws_handlers.send_email.handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.send_email,
    aws_ses_email_identity.from,
    aws_ses_email_identity.to,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "finalize" {
  function_name    = "${local.name_prefix}-finalize"
  role             = aws_iam_role.lambda.arn
  handler          = "claims_intake.aws_handlers.finalize.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.finalize,
    null_resource.account_guard,
  ]
}

# --- Step Functions ---
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name_prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn_policy" {
  statement {
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.ingest.arn,
      aws_lambda_function.process.arn,
      aws_lambda_function.wait_review.arn,
      aws_lambda_function.send_email.arn,
      aws_lambda_function.finalize.arn,
    ]
  }
  statement {
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${local.name_prefix}-sfn"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_policy.json
}

resource "aws_sfn_state_machine" "claim_intake" {
  name     = "${local.name_prefix}-claim-intake"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/../stepfunctions/claim_intake.asl.json", {
    ingest_lambda_arn      = aws_lambda_function.ingest.arn
    process_lambda_arn     = aws_lambda_function.process.arn
    wait_review_lambda_arn = aws_lambda_function.wait_review.arn
    send_email_lambda_arn  = aws_lambda_function.send_email.arn
    finalize_lambda_arn    = aws_lambda_function.finalize.arn
  })

  depends_on = [null_resource.account_guard]
}

# Local FastAPI operator permissions (SendTaskSuccess + DynamoDB + SES read of case)
data "aws_iam_policy_document" "operator" {
  statement {
    actions = [
      "states:SendTaskSuccess",
      "states:SendTaskFailure",
      "states:DescribeExecution",
      "states:GetExecutionHistory",
    ]
    resources = ["*"]
  }
  statement {
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

resource "aws_iam_user_policy" "operator" {
  name   = "${local.name_prefix}-operator-review"
  user   = var.operator_iam_user
  policy = data.aws_iam_policy_document.operator.json
}

# S3 → start execution via EventBridge-style notification through Lambda starter
data "aws_iam_policy_document" "starter_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "starter" {
  name               = "${local.name_prefix}-starter"
  assume_role_policy = data.aws_iam_policy_document.starter_assume.json
}

data "aws_iam_policy_document" "starter_policy" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.claim_intake.arn]
  }
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
  }
}

resource "aws_iam_role_policy" "starter" {
  name   = "${local.name_prefix}-starter"
  role   = aws_iam_role.starter.id
  policy = data.aws_iam_policy_document.starter_policy.json
}

resource "aws_lambda_function" "starter" {
  function_name = "${local.name_prefix}-starter"
  role          = aws_iam_role.starter.arn
  handler       = "claims_intake.aws_handlers.starter.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256
  filename      = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = {
      STATE_MACHINE_ARN = aws_sfn_state_machine.claim_intake.arn
    }
  }

  depends_on = [null_resource.lambda_package, null_resource.account_guard]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.starter.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.inbox.arn
}

resource "aws_s3_bucket_notification" "inbox" {
  bucket = aws_s3_bucket.inbox.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.starter.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".json"
  }
  depends_on = [aws_lambda_permission.allow_s3]
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "region" {
  value = var.aws_region
}

output "inbox_bucket" {
  value = aws_s3_bucket.inbox.bucket
}

output "cases_table" {
  value = aws_dynamodb_table.cases.name
}

output "audit_table" {
  value = aws_dynamodb_table.audit.name
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.claim_intake.arn
}

output "teardown" {
  value = "cd infra/terraform && terraform destroy -auto-approve"
}

output "ses_from_email" {
  value = var.ses_from_email
}

output "ses_to_email" {
  value = var.ses_to_email
}

output "ses_verify_note" {
  value = "Check ${var.ses_from_email} (and to, if different) for AWS SES verification emails before real sends work in sandbox."
}
