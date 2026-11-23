#!/usr/bin/env bash
# Sync the Vite SPA to the Terraform-managed UI bucket and invalidate CloudFront.
# Requires: enable_hosted_ui=true applied, AWS_PROFILE=personal
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF="$ROOT/infra/terraform"
PROFILE="${AWS_PROFILE:-personal}"
REGION="${AWS_REGION:-eu-north-1}"

BUCKET=$(cd "$TF" && AWS_PROFILE="$PROFILE" terraform output -raw ui_bucket 2>/dev/null || true)
DIST_ID=$(cd "$TF" && AWS_PROFILE="$PROFILE" terraform output -raw ui_cloudfront_distribution_id 2>/dev/null || true)
DOMAIN=$(cd "$TF" && AWS_PROFILE="$PROFILE" terraform output -raw ui_cloudfront_domain 2>/dev/null || true)

if [[ -z "$BUCKET" || "$BUCKET" == "null" ]]; then
  echo "ui_bucket empty — apply with -var='enable_hosted_ui=true' first" >&2
  exit 1
fi

cd "$ROOT/frontend"
npm ci
npm run build

aws s3 sync dist/ "s3://${BUCKET}/" --delete --profile "$PROFILE" --region "$REGION"

if [[ -n "$DIST_ID" && "$DIST_ID" != "null" ]]; then
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' --profile "$PROFILE"
fi

echo "Deployed → https://${DOMAIN}"
echo "Add that origin to cors_origins and re-apply API CORS if not already set."
