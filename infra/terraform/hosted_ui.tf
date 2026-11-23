# Hosted adjuster SPA (S3 + CloudFront). Off by default — enable after CloudFront
# is available on the account, then: terraform apply -var='enable_hosted_ui=true'
# and run frontend/scripts/deploy-ui.sh

resource "aws_s3_bucket" "ui" {
  count         = var.enable_hosted_ui ? 1 : 0
  bucket_prefix = "${local.name_prefix}-ui-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "ui" {
  count                   = var.enable_hosted_ui ? 1 : 0
  bucket                  = aws_s3_bucket.ui[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ui" {
  count  = var.enable_hosted_ui ? 1 : 0
  bucket = aws_s3_bucket.ui[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "ui" {
  count                             = var.enable_hosted_ui ? 1 : 0
  name                              = "${local.name_prefix}-ui-oac"
  description                       = "OAC for adjuster SPA"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "ui" {
  count               = var.enable_hosted_ui ? 1 : 0
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${local.name_prefix} adjuster UI"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.ui[0].bucket_regional_domain_name
    origin_id                = "ui-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.ui[0].id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "ui-s3"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  # SPA deep links → index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  depends_on = [null_resource.account_guard]
}

data "aws_iam_policy_document" "ui_bucket" {
  count = var.enable_hosted_ui ? 1 : 0
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.ui[0].arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.ui[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "ui" {
  count  = var.enable_hosted_ui ? 1 : 0
  bucket = aws_s3_bucket.ui[0].id
  policy = data.aws_iam_policy_document.ui_bucket[0].json
}

output "ui_bucket" {
  value = var.enable_hosted_ui ? aws_s3_bucket.ui[0].bucket : null
}

output "ui_cloudfront_domain" {
  value = var.enable_hosted_ui ? aws_cloudfront_distribution.ui[0].domain_name : null
}

output "ui_cloudfront_distribution_id" {
  value = var.enable_hosted_ui ? aws_cloudfront_distribution.ui[0].id : null
}

output "ui_url" {
  value = var.enable_hosted_ui ? "https://${aws_cloudfront_distribution.ui[0].domain_name}" : null
}

output "ui_deploy_hint" {
  value = var.enable_hosted_ui ? join("\n", [
    "Build & sync:",
    "  bash frontend/scripts/deploy-ui.sh",
    "Or manually:",
    "  cd frontend && npm run build",
    "  aws s3 sync dist/ s3://${aws_s3_bucket.ui[0].bucket}/ --delete --profile personal",
    "  aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.ui[0].id} --paths '/*' --profile personal",
    "Then add https://${aws_cloudfront_distribution.ui[0].domain_name} to cors_origins and re-apply API CORS.",
  ]) : null
}
