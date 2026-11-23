# Security overview — AI claims intake

One-pager for IT / security review. Not a formal audit attestation. Demo branding
(“Elm & Stone”) is fictional; treat the stack as a reference deploy in a customer
AWS account.

## Data residency

- Deploy target: customer AWS account, region `eu-north-1` (Stockholm).
- Claim packages land in a private S3 inbox (`inbox/`); optional raw inbound mail under `email-raw/`.
- Case state and audit events in DynamoDB.
- Model calls use Amazon Bedrock in-region (`CLAIMS_MODEL_ID`, default Nova Micro EU inference profile).
- SES *receiving* (when `enable_inbound_email`) uses a receiving-capable region (default `eu-west-1`); objects are written into the Stockholm inbox bucket.

## Human oversight

- The system classifies, extracts, checks, summarises, and drafts. It does **not** approve or deny claims.
- Outbound claimant messages require a **signed, single-use** HMAC token bound to the exact draft payload. The review API issues the token; **SendEmail verifies and atomically consumes** it before SES. Reuse fails a DynamoDB condition.
- Audit events record which Cognito adjuster approved.
- Adjuster field corrections are stored on the case and appended to the audit table; AI originals remain available for comparison.

## Access control

- Terraform creates **per-Lambda** IAM roles (ProcessClaim can call Bedrock but cannot send email or resume the workflow; SendEmail cannot call Bedrock).
- Hosted adjuster API: Cognito user pool + API Gateway HTTP API JWT authorizer; SPA sends the Cognito **ID token** as `Authorization: Bearer`.
- Hosted SPA (`enable_hosted_ui`): S3 origin is private; CloudFront Origin Access Control only. Add the CloudFront HTTPS origin to `cors_origins`.
- Local FastAPI remains available for operators with an IAM user profile (SendTaskSuccess / DynamoDB) when Cognito env vars are unset.
- Terraform apply refuses to proceed unless the caller account id matches the configured target account.
- Approval HMAC lives in **Secrets Manager** (generated `random_password`); Cognito adjuster password is also generated (see `terraform output -raw adjuster_password`).

## Encryption & logging

- S3 default encryption (AES256); DynamoDB SSE enabled.
- Customer-managed KMS key provisioned for secrets / future envelope encryption.
- CloudWatch logs retained 14 days for Lambda.
- Pipeline steps emit audit events: component, action, optional model version, and structured output.

## Mail

- **Outbound:** SES sends only after adjuster approval resumes the Step Functions wait token. Sandbox accounts must verify From and To identities before live delivery.
- **Inbound (optional):** SES receipt rule stores raw MIME under `email-raw/`; EmailIngest Lambda parses to a claim package and writes `inbox/*.json`. Domain ownership + MX are required before enabling.

## Teardown

```bash
cd infra/terraform && AWS_PROFILE=personal terraform destroy -auto-approve
```

Confirm `terraform output account_id` matches the intended account before apply or destroy.
