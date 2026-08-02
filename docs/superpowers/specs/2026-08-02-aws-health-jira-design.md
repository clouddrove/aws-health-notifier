# Design: Automated Jira Ticket Creation for AWS EC2 Scheduled Events

- **Date:** 2026-08-02
- **Status:** Approved (design), pending spec review
- **Owner:** anmol@clouddrove.com

## 1. Problem

AWS emits scheduled maintenance and retirement notifications for EC2 instances
(via AWS Health). Today these are easy to miss. We want each relevant event to
automatically become a tracked Jira Cloud ticket, and to be closed automatically
when the underlying event resolves, across an entire AWS Organization.

## 2. Approach

Chosen approach **B**: EventBridge rule targets a Lambda function that talks
directly to the Jira Cloud REST API. This avoids the Atlassian AWS Service
Management Connector (which requires a paid Jira Service Management tier and
offers no enrichment, dedup, or auto-close). It is cheaper (~$0.40/mo) and works
with any Jira Cloud project.

Rejected:
- **A (SMC connector):** JSM license lock-in, no enrichment/dedup/lifecycle.
- **C (Lambda + SQS front buffer):** premature for low-volume Health events.
  EventBridge async invoke + DLQ already provides durability. Design stays
  C-ready (handler is queue-agnostic) so SQS can slot in front later.

## 3. Architecture

```
Member accounts ──(AWS Health org-view events)──▶ Central Ops account
                                                     │
                                    EventBridge rule (source: aws.health,
                                    service: EC2, scheduled-change events)
                                                     │
                                          Lambda (Python 3.13)
                                          ├─ dedup / lifecycle  ─▶ DynamoDB
                                          ├─ enrich (event payload only, B1)
                                          ├─ priority map
                                          └─ Jira REST v3: create / comment / transition
                                                     │
                                          async failure ─▶ SQS DLQ
```

### 3.1 Scope: org-wide (delegated)
AWS Health organizational view is enabled by registering the central ops account
as a delegated administrator for `health.amazonaws.com`. All member-account EC2
Health events then surface in the central account's default event bus, where a
single EventBridge rule and a single Lambda handle them. No per-member-account
resources are deployed (enrichment is B1, payload-only).

## 4. Components

### 4.1 EventBridge rule
- Event pattern: `source = ["aws.health"]`, `detail-type = ["AWS Health Event"]`,
  filtered to `detail.service = ["EC2"]` and scheduled-change / retirement
  event type categories (`scheduledChange`, `issue` as configured).
- Target: the Lambda. Async invocation with a retry policy and an on-failure
  destination (SQS DLQ).

### 4.2 Lambda handler (Python 3.13)
Single function, modular internals:
- `handler.py` — entrypoint, orchestrates parse → lifecycle decision → Jira call.
- `events.py` — parse AWS Health event, extract `eventArn`, `statusCode`,
  affected entities, account, region, timeline.
- `enrich.py` — build ticket fields from event payload only (B1). Exposes a
  single `enrich(event) -> dict` hook so B2 (cross-account DescribeInstances) can
  be added later without touching the handler.
- `jira.py` — Jira Cloud REST v3 client (create issue, add comment, transition).
  Auth: email + API token from Secrets Manager, HTTP Basic.
- `state.py` — DynamoDB access: map `eventArn` → `issueKey` + `status`, with TTL.
- `config.py` — env-driven config (project key, issue type, priority map, table
  name, secret ARN).

### 4.3 DynamoDB table (application state)
- PK: `eventArn` (string). Attributes: `issueKey`, `status`, `updatedAt`, `ttl`.
- On-demand billing. TTL auto-expires closed events (e.g. 90 days).
- Serves **both** dedup (seen this event?) and auto-close (which ticket to close?).

### 4.4 Secrets Manager
- One secret holding Jira `{ base_url, email, api_token }`.
- Lambda granted `secretsmanager:GetSecretValue` on that ARN only.

### 4.5 SQS DLQ
- On-failure destination for the async Lambda invoke. Alarmed (optional
  CloudWatch alarm on `ApproximateNumberOfMessagesVisible > 0`).

## 5. Lifecycle logic

Driven by AWS Health `statusCode` and DynamoDB state:

| Event state | In DDB? | Action |
|---|---|---|
| `open` / `upcoming` | no | Create Jira ticket, enrich, store `eventArn→issueKey` |
| `open` / `upcoming` | yes | Dedup: add a comment if payload changed, else skip |
| `closed` / `resolved` | yes | Comment + transition ticket to Done, mark DDB `closed` |
| `closed` / `resolved` | no | No-op (never tracked) |

### 5.1 Priority mapping
Config-driven map from event type category to Jira priority, e.g.:
- `AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED` → High
- reboot / maintenance scheduled → Medium
- default → Low
Overridable via env/Terraform variable.

## 6. Enrichment (B1, payload-only)

Ticket body built from the Health event: account ID, region, affected instance
IDs, event type code, human description, and the event timeline (start/end).
No cross-account API calls, no member-account footprint. `enrich()` is isolated
so B2 (assume-role DescribeInstances for Name/env tags) can be added later.

## 7. Error handling

- Jira 5xx / network: exception bubbles → EventBridge async retry → DLQ.
- Jira 4xx (bad request): logged with context, sent to DLQ (not retried blindly).
- DynamoDB conditional writes prevent duplicate ticket creation on concurrent
  redelivery (create only if `eventArn` absent).
- All logs structured JSON to CloudWatch.

## 8. Testing

- **pytest** unit tests for each module.
- **moto** to mock DynamoDB / Secrets Manager.
- **responses** to mock the Jira REST API.
- Fixtures: sample AWS Health EC2 scheduled-change and resolved event payloads.
- Cases: create, dedup skip, auto-close, priority mapping, malformed event,
  Jira failure → exception path.

## 9. Repository layout

```
terraform/
  versions.tf        # terraform >= 1.10, aws provider ~> 6.57
  backend.tf         # S3 backend, native lockfile (use_lockfile = true), NO DynamoDB
  main.tf            # EventBridge rule, Lambda, IAM, DynamoDB (app state), SQS DLQ
  variables.tf
  outputs.tf
src/handler/
  handler.py events.py enrich.py jira.py state.py config.py
tests/
  test_handler.py test_jira.py test_state.py fixtures/
Dockerfile           # dev/CI image: python + ruff + mypy + pytest + tflint + checkov
Makefile             # lint / test / fmt / plan / package
.pre-commit-config.yaml
.github/workflows/ci.yml
README.md
```

## 10. Tooling & quality (best-in-class)

- **Python:** ruff (lint + format), mypy (strict types), pytest + moto + responses.
- **Terraform:** terraform fmt, terraform validate, tflint, checkov (security).
- **pre-commit** wiring all hooks; enforced again in CI.
- **CI (GitHub Actions):** ruff → mypy → pytest → tf fmt/validate → tflint → checkov.
- **Packaging:** Lambda built as a zip (fast cold start). Docker is dev/CI only.
- **Security:** Secrets Manager for Jira token, least-privilege IAM, DLQ,
  no secrets in env/state.

Exact tool/provider versions are pinned to latest stable at implementation time
(verified against registries, not guessed). Confirmed at design time:
AWS provider latest `6.57.1`; Lambda runtime Python 3.13.

## 11. State backend

S3 backend with native S3 lockfile (`use_lockfile = true`, Terraform ≥ 1.10).
No DynamoDB lock table. Bucket name supplied via backend config at init.

## 12. Cost

| Item | Monthly |
|---|---|
| EventBridge (AWS events) | $0 |
| Lambda | ~$0 (free tier) |
| DynamoDB on-demand | ~$0 |
| SQS DLQ | ~$0 |
| Secrets Manager | $0.40 |
| **Total** | **~$0.40** |

## 13. Out of scope (YAGNI)

- SQS front buffer (approach C) — add only if Jira 429s or dropped-ticket
  incident occurs.
- B2 cross-account instance-tag enrichment — hook reserved, not built.
- Non-EC2 Health events, non-Jira-Cloud targets, multi-region rules.
