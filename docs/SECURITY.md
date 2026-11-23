# Security overview — Elm & Stone claims intake

One-pager for IT / security review. Not a formal audit attestation.

## Data residency

- Deploy target: customer AWS account, region `eu-north-1` (Stockholm).
- Claim packages land in a private S3 inbox; case state and audit events in DynamoDB.
- Model calls use Amazon Bedrock in-region (`CLAIMS_MODEL_ID`, default Nova Micro EU inference profile).

## Human oversight

- The system classifies, extracts, checks, summarises, and drafts. It does **not** approve or deny claims.
- Outbound claimant messages require a **signed, single-use** HMAC token bound to the exact draft payload (claim id, action, body, recipients).
- Adjuster field corrections are stored on the case and appended to the audit table; AI originals remain available for comparison.

## Access control

- Terraform creates least-privilege IAM roles for Lambdas and Step Functions (no long-lived keys in compute).
- Day-to-day operators use a dedicated IAM user via a named AWS CLI profile — not account root.
- Terraform apply refuses to proceed unless the caller account id matches the configured target account.

## Encryption & logging

- S3 default encryption (AES256); DynamoDB SSE enabled.
- Customer-managed KMS key provisioned for secrets / future envelope encryption.
- CloudWatch logs retained 14 days for Lambda.
- Pipeline steps emit audit events: component, action, optional model version, and structured output.

## Outbound mail

- SES sends only after adjuster approval resumes the Step Functions wait token.
- Sandbox accounts must verify From and To identities before live delivery.

## Teardown

```bash
cd infra/terraform && AWS_PROFILE=personal terraform destroy -auto-approve
```

Confirm `terraform output account_id` matches the intended account before apply or destroy.
