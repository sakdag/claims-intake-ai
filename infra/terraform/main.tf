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
      error_message = "Refusing to deploy: account ${data.aws_caller_identity.current.account_id} != allowed ${var.allowed_account_id}."
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
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/email_ingest.py"),
      filesha256("${path.module}/../../src/claims_intake/aws_handlers/secrets.py"),
      filesha256("${path.module}/../../src/claims_intake/api/app.py"),
      filesha256("${path.module}/../../src/claims_intake/api/lambda_handler.py"),
      filesha256("${path.module}/../../src/claims_intake/pipeline/ingest.py"),
      filesha256("${path.module}/../../src/claims_intake/pipeline/claim_view.py"),
      filesha256("${path.module}/../../src/claims_intake/pipeline/email_ingest.py"),
      filesha256("${path.module}/../../src/claims_intake/pipeline/extract.py"),
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

# Per-function roles live in iam_lambdas.tf (least privilege).

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
    CLAIMS_AWS_REGION               = var.aws_region
    CLAIMS_AWS_PROFILE              = ""
    CLAIMS_MODEL_PROVIDER           = "bedrock"
    CLAIMS_MODEL_ID                 = var.model_id
    CASES_TABLE                     = aws_dynamodb_table.cases.name
    AUDIT_TABLE                     = aws_dynamodb_table.audit.name
    CLAIMS_APPROVAL_HMAC_SECRET_ARN = aws_secretsmanager_secret.approval_hmac.arn
    SES_FROM_EMAIL                  = var.ses_from_email
    SES_TO_EMAIL                    = var.ses_to_email
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
  role          = aws_iam_role.lambda_ingest.arn
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
    aws_iam_role_policy.lambda_ingest,
    aws_cloudwatch_log_group.ingest,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "process" {
  function_name    = "${local.name_prefix}-process"
  role             = aws_iam_role.lambda_process.arn
  handler          = "claims_intake.aws_handlers.process_claim.handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 1024
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda_process,
    aws_cloudwatch_log_group.process,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "wait_review" {
  function_name    = "${local.name_prefix}-wait-review"
  role             = aws_iam_role.lambda_wait.arn
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
    aws_iam_role_policy.lambda_wait,
    aws_cloudwatch_log_group.wait_review,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "send_email" {
  function_name    = "${local.name_prefix}-send-email"
  role             = aws_iam_role.lambda_send.arn
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
    aws_iam_role_policy.lambda_send,
    aws_cloudwatch_log_group.send_email,
    aws_ses_email_identity.from,
    aws_ses_email_identity.to,
    null_resource.account_guard,
  ]
}

resource "aws_lambda_function" "finalize" {
  function_name    = "${local.name_prefix}-finalize"
  role             = aws_iam_role.lambda_finalize.arn
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
    aws_iam_role_policy.lambda_finalize,
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
  function_name    = "${local.name_prefix}-starter"
  role             = aws_iam_role.starter.arn
  handler          = "claims_intake.aws_handlers.starter.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  filename         = local.lambda_zip
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

# When enable_inbound_email=true, inbound_email.tf owns the notification
# (email-raw/ → EmailIngest + inbox/*.json → Starter).
resource "aws_s3_bucket_notification" "inbox" {
  count  = var.enable_inbound_email ? 0 : 1
  bucket = aws_s3_bucket.inbox.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.starter.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "inbox/"
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

# --- Hosted adjuster API (Cognito JWT → API Gateway → Lambda) ---
# SPA stays on local Vite until CloudFront is available; point VITE_API_BASE at api_base_url.

resource "aws_cognito_user_pool" "adjusters" {
  count = var.enable_hosted_api ? 1 : 0
  name  = "${local.name_prefix}-adjusters"

  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "spa" {
  count        = var.enable_hosted_api ? 1 : 0
  name         = "${local.name_prefix}-spa"
  user_pool_id = aws_cognito_user_pool.adjusters[0].id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  allowed_oauth_flows_user_pool_client = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_cognito_user" "adjuster" {
  count        = var.enable_hosted_api ? 1 : 0
  user_pool_id = aws_cognito_user_pool.adjusters[0].id
  username     = var.adjuster_username
  password     = random_password.adjuster.result

  attributes = {
    email          = var.adjuster_email
    email_verified = "true"
  }

  message_action = "SUPPRESS"

  lifecycle {
    ignore_changes = [password, attributes]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  count             = var.enable_hosted_api ? 1 : 0
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  count            = var.enable_hosted_api ? 1 : 0
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.lambda_api.arn
  handler          = "claims_intake.api.lambda_handler.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 512
  filename         = local.lambda_zip
  source_code_hash = base64encode(null_resource.lambda_package.triggers.code_hash)

  environment {
    variables = merge(local.lambda_env, {
      CORS_ORIGINS = join(",", var.cors_origins)
    })
  }

  depends_on = [
    null_resource.lambda_package,
    aws_iam_role_policy.lambda_api,
    aws_cloudwatch_log_group.api,
    null_resource.account_guard,
  ]
}

resource "aws_apigatewayv2_api" "review" {
  count         = var.enable_hosted_api ? 1 : 0
  name          = "${local.name_prefix}-review-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["authorization", "content-type"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_origins = var.cors_origins
    max_age       = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  count            = var.enable_hosted_api ? 1 : 0
  api_id           = aws_apigatewayv2_api.review[0].id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.spa[0].id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.adjusters[0].id}"
  }
}

resource "aws_apigatewayv2_integration" "api" {
  count                  = var.enable_hosted_api ? 1 : 0
  api_id                 = aws_apigatewayv2_api.review[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api[0].invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "health" {
  count     = var.enable_hosted_api ? 1 : 0
  api_id    = aws_apigatewayv2_api.review[0].id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.api[0].id}"
}

# Use GET/POST only — ANY would also match OPTIONS and break browser CORS
# preflight (JWT authorizer returns 401 before the CORS auto-response).
resource "aws_apigatewayv2_route" "proxy_get" {
  count              = var.enable_hosted_api ? 1 : 0
  api_id             = aws_apigatewayv2_api.review[0].id
  route_key          = "GET /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito[0].id
}

resource "aws_apigatewayv2_route" "proxy_post" {
  count              = var.enable_hosted_api ? 1 : 0
  api_id             = aws_apigatewayv2_api.review[0].id
  route_key          = "POST /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito[0].id
}

resource "aws_apigatewayv2_route" "root_get" {
  count              = var.enable_hosted_api ? 1 : 0
  api_id             = aws_apigatewayv2_api.review[0].id
  route_key          = "GET /"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito[0].id
}

resource "aws_apigatewayv2_route" "root_post" {
  count              = var.enable_hosted_api ? 1 : 0
  api_id             = aws_apigatewayv2_api.review[0].id
  route_key          = "POST /"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito[0].id
}

resource "aws_apigatewayv2_stage" "default" {
  count       = var.enable_hosted_api ? 1 : 0
  api_id      = aws_apigatewayv2_api.review[0].id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw_api" {
  count         = var.enable_hosted_api ? 1 : 0
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.review[0].execution_arn}/*/*"
}

output "api_base_url" {
  value = var.enable_hosted_api ? aws_apigatewayv2_api.review[0].api_endpoint : null
}

output "cognito_user_pool_id" {
  value = var.enable_hosted_api ? aws_cognito_user_pool.adjusters[0].id : null
}

output "cognito_client_id" {
  value = var.enable_hosted_api ? aws_cognito_user_pool_client.spa[0].id : null
}

output "cognito_region" {
  value = var.enable_hosted_api ? var.aws_region : null
}

output "adjuster_username" {
  value = var.enable_hosted_api ? var.adjuster_username : null
}

output "frontend_env_hint" {
  value = var.enable_hosted_api ? join("\n", [
    "VITE_API_BASE=${aws_apigatewayv2_api.review[0].api_endpoint}",
    "VITE_COGNITO_REGION=${var.aws_region}",
    "VITE_COGNITO_USER_POOL_ID=${aws_cognito_user_pool.adjusters[0].id}",
    "VITE_COGNITO_CLIENT_ID=${aws_cognito_user_pool_client.spa[0].id}",
  ]) : null
}
