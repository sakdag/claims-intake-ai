# Teardown

Destroy the stack when you are finished with a deploy cycle to avoid idle cost.

```bash
cd infra/terraform
export AWS_PROFILE=personal
terraform destroy -auto-approve
```

Confirm `terraform output account_id` is the intended account before apply or destroy.

## Cost note

A short-lived cycle (package → apply → a few Bedrock claim runs / HITL smokes → destroy)
is expected to stay well under a few USD in `eu-north-1` with Nova Micro. Main drivers:

- Bedrock tokens (classify + extract per document)
- Lambda + Step Functions execution
- DynamoDB on-demand, S3, CloudWatch logs, SES (sandbox)

Idle stacks still accrue small DynamoDB / log storage charges — prefer destroy over overnight leave-up.
