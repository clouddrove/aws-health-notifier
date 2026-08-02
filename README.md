# AWS Health to Jira Ticket Automation

Automatically create, dedup, and auto-close Jira Cloud tickets from AWS Health
EC2 scheduled-change events across an AWS Organization. Deployed entirely by
Terraform.

## Architecture

```
Member accounts ──(AWS Health org events)──▶ Central Ops account
                                                │
                             EventBridge rule (aws.health, service=EC2)
                                                │
                                     Lambda (Python 3.13)
                                     ├─ dedup / lifecycle ─▶ DynamoDB
                                     ├─ enrich (event payload only)
                                     ├─ priority map
                                     └─ Jira REST v3: create / comment / transition
                                                │
                                     async failure ─▶ SQS DLQ
```

See the design spec in `docs/superpowers/specs/` and the implementation plan in
`docs/superpowers/plans/`.

## Prerequisites

- An AWS account designated as the central operations account.
- Terraform >= 1.10, AWS provider ~> 6.57.
- A Jira Cloud project with permission to create issues, add comments, and
  transition issues.
- An S3 bucket for Terraform state (native lockfile, no DynamoDB lock table).

## Cost

Around $0.40/month (Secrets Manager). EventBridge, Lambda, DynamoDB on-demand,
and the SQS DLQ sit within free-tier usage at Health-event volume.

## Setup

### 1. Enable org-wide AWS Health (one time, management account)

AWS Health organizational view surfaces member-account events on the central
account bus. Register the central account as delegated administrator:

```bash
aws organizations register-delegated-administrator \
  --account-id <CENTRAL_OPS_ACCOUNT_ID> \
  --service-principal health.amazonaws.com
```

This is an organization-management action, run once outside Terraform.

### 2. Create the Jira secret (central account)

Store Jira credentials in Secrets Manager as JSON:

```json
{
  "base_url": "https://your-domain.atlassian.net",
  "email": "automation@your-domain.com",
  "api_token": "<jira-api-token>"
}
```

```bash
aws secretsmanager create-secret \
  --name aws-health-jira/creds \
  --secret-string file://jira-creds.json
```

Note the returned ARN for `jira_secret_arn`.

### 3. Package the Lambda

```bash
make package   # produces dist/handler.zip
```

### 4. Deploy

```bash
cd terraform
terraform init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=aws-health-jira/terraform.tfstate" \
  -backend-config="region=<region>"
terraform apply -var-file=terraform.tfvars
```

See `terraform/terraform.tfvars.example` for variables.

## Development

```bash
make lint      # ruff + mypy
make test      # pytest (moto + responses, no AWS or Jira needed)
make package   # build Lambda zip
make tf-validate
```

Docker image (`Dockerfile`) bundles the full dev/CI toolchain and is used by CI
only; the Lambda itself ships as a zip.
