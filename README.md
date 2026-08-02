# aws-health-notifier

Turn AWS Health EC2 scheduled events (maintenance, retirement, reboots) into
tracked tickets, automatically, across an AWS Organization. Jira Cloud is the
first notifier; the sink is pluggable, so Slack or PagerDuty can be added later
without touching the core.

## Why not the AWS Service Management Connector

The Atlassian connector needs a paid Jira Service Management tier and gives no
enrichment, no dedup, and no auto-close. This talks to the Jira REST API
directly from a small Lambda: it works with any Jira Cloud project, enriches the
ticket, dedups, and closes the ticket when the event resolves. Running cost is
about $0.40/month.

## Architecture

```
Member accounts ──(AWS Health org events)──▶ Central Ops account
                                                │
                             EventBridge rule (aws.health, service=EC2)
                                                │
                                     Lambda (Python 3.13)
                                     ├─ dedup / lifecycle ─▶ DynamoDB (eventArn ▶ ref)
                                     ├─ enrich (event payload only)
                                     ├─ priority map
                                     └─ Notifier ─▶ Jira REST v3 (create / comment / transition)
                                                │
                                     async failure ─▶ SQS DLQ
```

The Lambda is sink-agnostic. It calls a `Notifier` interface; `NOTIFIER=jira`
selects the Jira implementation. Adding a sink is a new module under
`src/handler/notifiers/` plus one branch in the factory.

Lifecycle, driven by the Health `statusCode` and DynamoDB state:

| Event state | Tracked in DynamoDB | Action |
|---|---|---|
| open / upcoming | no | create ticket, store `eventArn ▶ ref` |
| open / upcoming | yes | dedup, no new ticket |
| closed / resolved | yes, still open | comment + transition to Done, mark closed |
| closed / resolved | yes, already closed | skip (idempotent) |
| closed / resolved | no | ignore (never created a ticket) |

## Repository layout

```
src/handler/
  handler.py            Lambda entrypoint, sink-agnostic orchestration
  config.py             env-driven configuration
  events.py             parse AWS Health events
  enrich.py             build ticket fields from the event payload (Jira ADF)
  state.py              DynamoDB dedup + lifecycle
  secrets.py            read the notifier secret
  jira.py               low-level Jira Cloud REST v3 client
  notifiers/
    base.py             Notifier protocol
    jira_notifier.py    Jira implementation
    __init__.py         build(cfg) factory
terraform/              EventBridge, Lambda, IAM, DynamoDB, SQS DLQ, S3 backend
tests/                  pytest, moto (AWS), urllib mocking (Jira)
.github/workflows/      ci.yml (checks) and deploy.yml (OIDC apply)
```

## Prerequisites

- A central operations AWS account.
- Terraform >= 1.10, AWS provider ~> 6.57.
- A Jira Cloud project with permission to create issues, add comments, and
  transition issues.
- An S3 bucket for Terraform state (native lockfile, no DynamoDB lock table).

## Setup

### 1. Enable org-wide AWS Health (one time, management account)

```bash
aws organizations register-delegated-administrator \
  --account-id <CENTRAL_OPS_ACCOUNT_ID> \
  --service-principal health.amazonaws.com
```

This is an organization-management action, run once outside Terraform. It makes
member-account EC2 Health events surface on the central account event bus.

### 2. Create the notifier secret (central account)

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
  --name aws-health-notifier/creds \
  --secret-string file://jira-creds.json
```

Note the returned ARN for `jira_secret_arn`.

### 3. Deploy

```bash
make package        # builds dist/handler.zip
cd terraform
terraform init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=aws-health-notifier/terraform.tfstate" \
  -backend-config="region=<region>"
terraform apply -var-file=terraform.tfvars
```

See `terraform/terraform.tfvars.example` for the variables.

## GitHub Actions

Everything runs in CI, and deploys can run from Actions too.

- **`ci.yml`** (every push and PR): ruff lint + format check, mypy strict,
  pytest, a package-and-import check on the Lambda zip, then terraform fmt,
  validate, tflint, and checkov.
- **`deploy.yml`** (push to `main`, or manual): builds the zip, assumes an AWS
  role via GitHub OIDC (no static keys), and runs `terraform apply`.

Configure these repo-level Actions variables for deploy:

| Variable | Purpose |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | IAM role the workflow assumes via OIDC |
| `AWS_REGION` | deployment region |
| `TF_STATE_BUCKET` | S3 bucket holding Terraform state |
| `JIRA_PROJECT_KEY` | Jira project for tickets |
| `JIRA_SECRET_ARN` | ARN of the Secrets Manager secret from step 2 |
| `NOTIFIER` | optional, notifier backend, defaults to `jira` |

The IAM role's trust policy must allow this repository's OIDC subject
(`token.actions.githubusercontent.com`).

## Configuration

| Env var (Lambda) | Terraform variable | Default |
|---|---|---|
| `NOTIFIER` | `notifier` | `jira` |
| `JIRA_PROJECT_KEY` | `jira_project_key` | required |
| `JIRA_ISSUE_TYPE` | `jira_issue_type` | `Task` |
| `DEFAULT_PRIORITY` | `default_priority` | `Low` |
| `PRIORITY_MAP_JSON` | `priority_map` | retirement ▶ High |
| `DONE_TRANSITION` | `done_transition` | `Done` |
| `TABLE_NAME` | (set by Terraform) | - |
| `SECRET_ARN` | `jira_secret_arn` | required |

## Development

```bash
make lint        # ruff + mypy
make test        # pytest (moto + urllib mocking, no AWS or Jira needed)
make package     # build the Lambda zip
make tf-validate # terraform fmt + tflint + checkov
```

The `Dockerfile` bundles the full dev/CI toolchain. The Lambda itself ships as a
zip, not a container.

## Cost

| Item | Monthly |
|---|---|
| EventBridge (AWS events) | $0 |
| Lambda | ~$0 (free tier) |
| DynamoDB on-demand | ~$0 |
| SQS DLQ | ~$0 |
| Secrets Manager | $0.40 |
| **Total** | **~$0.40** |
