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
                                     └─ Notifier ─▶ Jira REST v3 or GitHub Issues
                                                │       (create / comment / close)
                                     async failure ─▶ SQS DLQ
```

The Lambda is sink-agnostic. It calls a `Notifier` interface; `NOTIFIER=jira|github`
selects the implementation. Adding a sink is a new subpackage under
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
  state.py              DynamoDB dedup + lifecycle
  secrets.py            read the notifier secret
  logging.py            structured JSON logging
  notifiers/
    base.py             Notifier protocol + NotifierError
    priority.py         event type to priority mapping
    __init__.py         build(cfg) factory
    jira/               client.py, format.py (ADF), notifier.py
    github/             client.py, format.py (markdown), notifier.py
terraform/              EventBridge, Lambda, IAM, DynamoDB, SQS DLQ, S3 backend
tests/                  pytest, moto (AWS), urllib mocking (Jira and GitHub)
.github/workflows/      ci.yml (checks) and deploy.yml (OIDC apply)
```

## Prerequisites

- A central operations AWS account.
- Terraform >= 1.10, AWS provider ~> 6.57.
- A notifier target: a Jira Cloud project (create/comment/transition) or a
  GitHub repo with a PAT that has issues read and write.
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

### 2. Choose a notifier and create its secret (central account)

Set `NOTIFIER` (Terraform var `notifier`) to `jira` or `github`. Store that
notifier's credentials in a Secrets Manager secret and pass its ARN as
`secret_arn`.

**Jira** (`NOTIFIER=jira`) needs `JIRA_PROJECT_KEY` and a secret:

```json
{
  "base_url": "https://your-domain.atlassian.net",
  "email": "automation@your-domain.com",
  "api_token": "<jira-api-token>"
}
```

The Jira account needs permission to create issues, add comments, and
transition issues. Priority becomes the Jira priority name.

**GitHub Issues** (`NOTIFIER=github`) needs `GITHUB_REPO` (`owner/repo`) and a
secret:

```json
{
  "token": "<github-pat>",
  "api_url": "https://api.github.com"
}
```

`api_url` is optional (set it for GitHub Enterprise). The PAT needs issues read
and write on the target repo. Priority becomes a `priority:<level>` label, which
the notifier creates on the repo if missing.

```bash
aws secretsmanager create-secret \
  --name aws-health-notifier/creds \
  --secret-string file://creds.json
```

Note the returned ARN for `secret_arn`.

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
- **`deploy.yml`** (manual, from the Actions tab): assumes an AWS role via GitHub
  OIDC (no static keys) and runs `terraform apply` (Terraform builds the Lambda
  zip via the archive provider).

Configure these repo-level Actions variables for deploy:

| Variable | Purpose |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | IAM role the workflow assumes via OIDC |
| `AWS_REGION` | deployment region |
| `TF_STATE_BUCKET` | S3 bucket holding Terraform state |
| `SECRET_ARN` | ARN of the Secrets Manager secret from step 2 |
| `NOTIFIER` | optional, `jira` or `github`, defaults to `jira` |
| `JIRA_PROJECT_KEY` | Jira project for tickets (when notifier is jira) |
| `GITHUB_REPO` | owner/repo for issues (when notifier is github) |

The IAM role's trust policy must allow this repository's OIDC subject
(`token.actions.githubusercontent.com`).

## Configuration

| Env var (Lambda) | Terraform variable | Default |
|---|---|---|
| `NOTIFIER` | `notifier` | `jira` |
| `SECRET_ARN` | `secret_arn` | required |
| `GITHUB_REPO` | `github_repo` | `""` (required for github) |
| `JIRA_PROJECT_KEY` | `jira_project_key` | `""` (required for jira) |
| `JIRA_ISSUE_TYPE` | `jira_issue_type` | `Task` |
| `DEFAULT_PRIORITY` | `default_priority` | `Low` |
| `PRIORITY_MAP_JSON` | `priority_map` | retirement ▶ High |
| `DONE_TRANSITION` | `done_transition` | `Done` (jira only) |
| `TABLE_NAME` | (set by Terraform) | - |

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
