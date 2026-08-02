# AWS Health → Jira Ticket Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically create, dedup, and auto-close Jira Cloud tickets from AWS Health EC2 scheduled-change events across an AWS Organization, deployed entirely by Terraform.

**Architecture:** A single EventBridge rule in a central (delegated-admin) account routes org-wide AWS Health EC2 events to one Python 3.13 Lambda. The Lambda parses the event, uses a DynamoDB table to dedup and track lifecycle (`eventArn → issueKey`), enriches the ticket from the event payload only (B1), maps priority, and calls the Jira Cloud REST v3 API to create/comment/transition. Async invoke failures land in an SQS DLQ.

**Tech Stack:** Python 3.13, boto3, urllib (stdlib HTTP, no external Jira SDK), Terraform ≥ 1.10, AWS provider ~> 6.57, pytest + moto + responses, ruff, mypy, tflint, checkov, pre-commit, GitHub Actions, Docker (dev/CI only).

## Global Constraints

- Python runtime: **3.13** (Lambda + local).
- Terraform **≥ 1.10** (S3 native lockfile). AWS provider **~> 6.57** (latest 6.57.1 at design time; verify latest stable at implementation, do not guess).
- State backend: **S3 with `use_lockfile = true`**, NO DynamoDB lock table.
- Lambda packaged as **zip** (not container). Docker is dev/CI tooling only.
- Enrichment is **B1 (event payload only)** — no cross-account calls, no member-account resources.
- Jira Cloud auth: **email + API token** (HTTP Basic), token stored in **Secrets Manager**, never in env/state.
- No external Python deps in the Lambda runtime beyond boto3 (already in AWS runtime). Use stdlib `urllib.request` for Jira HTTP. Test-only deps: pytest, moto, responses.
- Writing style: no em dash, no `--`, no AI filler words (per repo CLAUDE.md).
- Commit messages: Conventional Commits, no AI attribution / Co-Authored-By trailers.
- IAM least-privilege: Lambda may only GetSecretValue on the one secret, read/write the one DynamoDB table, and send to the one DLQ.

---

### Task 0: Repo tooling bootstrap

**Files:**
- Create: `pyproject.toml`, `Makefile`, `Dockerfile`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `.gitignore`, `.dockerignore`, `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `make lint`, `make test`, `make fmt`, `make package`, `make plan` targets; CI pipeline. Later tasks assume `src/handler/` is on `PYTHONPATH` and tests live in `tests/`.

- [ ] **Step 1: Create `pyproject.toml`** (ruff + mypy + pytest config, no runtime deps)

```toml
[project]
name = "aws-health-jira"
version = "0.1.0"
requires-python = ">=3.13"

[dependency-groups]
dev = ["pytest", "moto[dynamodb,secretsmanager]", "responses", "ruff", "mypy", "boto3", "boto3-stubs[dynamodb,secretsmanager]"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "N"]

[tool.mypy]
python_version = "3.13"
strict = true
files = ["src", "tests"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `Makefile`**

```makefile
.PHONY: lint fmt test package plan tf-validate
lint:
	ruff check .
	ruff format --check .
	mypy
fmt:
	ruff format .
	ruff check --fix .
	terraform -chdir=terraform fmt
test:
	pytest -v
package:
	rm -rf build dist && mkdir -p dist
	cp -r src/handler build 2>/dev/null || (mkdir -p build && cp -r src/handler/* build/)
	cd build && zip -r ../dist/handler.zip . -x '*.pyc' '__pycache__/*'
tf-validate:
	terraform -chdir=terraform fmt -check
	tflint --chdir=terraform
	checkov -d terraform --quiet
plan:
	terraform -chdir=terraform plan
```

- [ ] **Step 3: Create `Dockerfile`** (dev/CI image; pin base to latest stable python:3.13-slim at implementation)

```dockerfile
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git zip curl unzip \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ruff mypy pytest "moto[dynamodb,secretsmanager]" responses \
    boto3 "boto3-stubs[dynamodb,secretsmanager]" checkov
# tflint
RUN curl -sSL https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
WORKDIR /work
```

- [ ] **Step 4: Create `.pre-commit-config.yaml`** (verify latest rev tags at implementation)

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1
    hooks:
      - id: mypy
        additional_dependencies: ["boto3-stubs[dynamodb,secretsmanager]"]
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.96.3
    hooks:
      - id: terraform_fmt
      - id: terraform_tflint
      - id: terraform_checkov
```

- [ ] **Step 5: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install ruff mypy pytest "moto[dynamodb,secretsmanager]" responses boto3 "boto3-stubs[dynamodb,secretsmanager]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy
      - run: pytest -v
      - uses: hashicorp/setup-terraform@v3
      - run: terraform -chdir=terraform fmt -check
      - run: terraform -chdir=terraform init -backend=false
      - run: terraform -chdir=terraform validate
      - uses: terraform-linters/setup-tflint@v4
      - run: tflint --chdir=terraform --init && tflint --chdir=terraform
      - uses: bridgecrewio/checkov-action@master
        with:
          directory: terraform
```

- [ ] **Step 6: Create `.gitignore`, `.dockerignore`, `README.md`** (README: overview, prerequisites, `terraform init` backend config, Jira secret format, make targets).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml Makefile Dockerfile .pre-commit-config.yaml .github .gitignore .dockerignore README.md
git commit -m "chore: bootstrap python + terraform tooling and CI"
```

---

### Task 1: Config and event parsing

**Files:**
- Create: `src/handler/config.py`, `src/handler/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces:
  - `config.load() -> Config` dataclass with fields: `project_key: str`, `issue_type: str`, `default_priority: str`, `priority_map: dict[str, str]`, `table_name: str`, `secret_arn: str`, `done_transition: str`. Reads from env vars `JIRA_PROJECT_KEY`, `JIRA_ISSUE_TYPE`, `DEFAULT_PRIORITY`, `PRIORITY_MAP_JSON`, `TABLE_NAME`, `SECRET_ARN`, `DONE_TRANSITION`.
  - `events.parse(raw: dict) -> HealthEvent | None` returns `None` for non-EC2 / irrelevant events. `HealthEvent` dataclass: `event_arn: str`, `event_type_code: str`, `status_code: str`, `account: str`, `region: str`, `entities: list[str]`, `description: str`, `start_time: str`, `end_time: str`.

- [ ] **Step 1: Write failing test** `tests/test_events.py`

```python
import json
from handler import config, events

RAW = {
    "detail-type": "AWS Health Event",
    "source": "aws.health",
    "account": "111122223333",
    "region": "us-east-1",
    "detail": {
        "eventArn": "arn:aws:health:us-east-1::event/EC2/AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED/abc",
        "service": "EC2",
        "eventTypeCode": "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
        "eventTypeCategory": "scheduledChange",
        "statusCode": "open",
        "startTime": "Wed, 1 Oct 2026 12:00:00 GMT",
        "endTime": "Wed, 1 Oct 2026 14:00:00 GMT",
        "eventDescription": [{"language": "en_US", "latestDescription": "Your instance is scheduled for retirement."}],
        "affectedEntities": [{"entityValue": "i-0abc123"}],
    },
}

def test_parse_extracts_fields():
    ev = events.parse(RAW)
    assert ev is not None
    assert ev.event_type_code == "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED"
    assert ev.status_code == "open"
    assert ev.account == "111122223333"
    assert ev.entities == ["i-0abc123"]

def test_parse_ignores_non_ec2():
    raw = {**RAW, "detail": {**RAW["detail"], "service": "RDS"}}
    assert events.parse(raw) is None

def test_config_priority_map(monkeypatch):
    monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
    monkeypatch.setenv("JIRA_ISSUE_TYPE", "Task")
    monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
    monkeypatch.setenv("PRIORITY_MAP_JSON", json.dumps({"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"}))
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("SECRET_ARN", "arn:secret")
    monkeypatch.setenv("DONE_TRANSITION", "Done")
    cfg = config.load()
    assert cfg.priority_map["AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED"] == "High"
    assert cfg.default_priority == "Low"
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_events.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `src/handler/config.py`**

```python
from __future__ import annotations
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    project_key: str
    issue_type: str
    default_priority: str
    priority_map: dict[str, str]
    table_name: str
    secret_arn: str
    done_transition: str


def load() -> Config:
    return Config(
        project_key=os.environ["JIRA_PROJECT_KEY"],
        issue_type=os.environ.get("JIRA_ISSUE_TYPE", "Task"),
        default_priority=os.environ.get("DEFAULT_PRIORITY", "Low"),
        priority_map=json.loads(os.environ.get("PRIORITY_MAP_JSON", "{}")),
        table_name=os.environ["TABLE_NAME"],
        secret_arn=os.environ["SECRET_ARN"],
        done_transition=os.environ.get("DONE_TRANSITION", "Done"),
    )
```

- [ ] **Step 4: Implement `src/handler/events.py`**

```python
from __future__ import annotations
from dataclasses import dataclass

_CLOSED = {"closed", "resolved"}


@dataclass(frozen=True)
class HealthEvent:
    event_arn: str
    event_type_code: str
    status_code: str
    account: str
    region: str
    entities: list[str]
    description: str
    start_time: str
    end_time: str

    @property
    def is_closed(self) -> bool:
        return self.status_code.lower() in _CLOSED


def parse(raw: dict) -> HealthEvent | None:
    if raw.get("source") != "aws.health":
        return None
    detail = raw.get("detail", {})
    if detail.get("service") != "EC2":
        return None
    descriptions = detail.get("eventDescription", [])
    description = descriptions[0].get("latestDescription", "") if descriptions else ""
    entities = [e.get("entityValue", "") for e in detail.get("affectedEntities", [])]
    return HealthEvent(
        event_arn=detail["eventArn"],
        event_type_code=detail.get("eventTypeCode", ""),
        status_code=detail.get("statusCode", "open"),
        account=raw.get("account", ""),
        region=raw.get("region", ""),
        entities=entities,
        description=description,
        start_time=detail.get("startTime", ""),
        end_time=detail.get("endTime", ""),
    )
```

- [ ] **Step 5: Run tests** — `pytest tests/test_events.py -v` → PASS. Run `ruff check . && mypy`.

- [ ] **Step 6: Commit** — `git commit -m "feat: add config loader and AWS Health event parser"`

---

### Task 2: Enrichment (B1)

**Files:**
- Create: `src/handler/enrich.py`
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `events.HealthEvent`, `config.Config`.
- Produces:
  - `enrich.priority(cfg: Config, ev: HealthEvent) -> str` — returns mapped priority or default.
  - `enrich.summary(ev: HealthEvent) -> str` — Jira summary line.
  - `enrich.description(ev: HealthEvent) -> dict` — Atlassian Document Format (ADF) doc for the Jira `description` field.

- [ ] **Step 1: Write failing test** `tests/test_enrich.py`

```python
from handler import enrich
from handler.config import Config
from handler.events import HealthEvent

CFG = Config("OPS", "Task", "Low", {"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"}, "t", "arn", "Done")
EV = HealthEvent("arn:...abc", "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED", "open",
                 "111122223333", "us-east-1", ["i-0abc123"], "Retirement scheduled.",
                 "Wed, 1 Oct 2026 12:00:00 GMT", "Wed, 1 Oct 2026 14:00:00 GMT")

def test_priority_mapped():
    assert enrich.priority(CFG, EV) == "High"

def test_priority_default():
    ev = HealthEvent("a", "SOME_OTHER_CODE", "open", "1", "us-east-1", [], "", "", "")
    assert enrich.priority(CFG, ev) == "Low"

def test_summary_contains_instance_and_account():
    s = enrich.summary(EV)
    assert "i-0abc123" in s and "111122223333" in s

def test_description_is_adf_doc():
    doc = enrich.description(EV)
    assert doc["type"] == "doc" and doc["version"] == 1
    assert any(block["type"] == "paragraph" for block in doc["content"])
```

- [ ] **Step 2: Run to verify fail** — FAIL (module missing).

- [ ] **Step 3: Implement `src/handler/enrich.py`**

```python
from __future__ import annotations
from .config import Config
from .events import HealthEvent


def priority(cfg: Config, ev: HealthEvent) -> str:
    return cfg.priority_map.get(ev.event_type_code, cfg.default_priority)


def summary(ev: HealthEvent) -> str:
    instances = ", ".join(ev.entities) or "unknown"
    return f"[AWS Health] {ev.event_type_code} - {instances} ({ev.account}/{ev.region})"


def _line(label: str, value: str) -> dict:
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": f"{label}: ", "marks": [{"type": "strong"}]},
            {"type": "text", "text": value or "-"},
        ],
    }


def description(ev: HealthEvent) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            _line("Account", ev.account),
            _line("Region", ev.region),
            _line("Event type", ev.event_type_code),
            _line("Status", ev.status_code),
            _line("Instances", ", ".join(ev.entities)),
            _line("Window", f"{ev.start_time} -> {ev.end_time}"),
            _line("Event ARN", ev.event_arn),
            {"type": "paragraph", "content": [{"type": "text", "text": ev.description or "-"}]},
        ],
    }
```

- [ ] **Step 4: Run tests** — PASS. `ruff check . && mypy`.

- [ ] **Step 5: Commit** — `git commit -m "feat: add payload-only ticket enrichment and priority mapping"`

---

### Task 3: Jira Cloud REST client

**Files:**
- Create: `src/handler/jira.py`
- Test: `tests/test_jira.py`

**Interfaces:**
- Consumes: Jira creds dict `{base_url, email, api_token}`.
- Produces:
  - `jira.JiraClient(base_url: str, email: str, api_token: str)`.
  - `.create_issue(project_key: str, issue_type: str, summary: str, description: dict, priority: str) -> str` returns issue key.
  - `.add_comment(issue_key: str, text: str) -> None`.
  - `.transition(issue_key: str, transition_name: str) -> None` (looks up transition id by name, no-op if not found).

- [ ] **Step 1: Write failing test** `tests/test_jira.py` (uses `responses`)

```python
import json
import responses
from handler.jira import JiraClient

BASE = "https://example.atlassian.net"
CLIENT = JiraClient(BASE, "me@x.com", "token")

@responses.activate
def test_create_issue_returns_key():
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue",
                  json={"key": "OPS-42"}, status=201)
    key = CLIENT.create_issue("OPS", "Task", "sum", {"type": "doc", "version": 1, "content": []}, "High")
    assert key == "OPS-42"
    body = json.loads(responses.calls[0].request.body)
    assert body["fields"]["project"]["key"] == "OPS"
    assert body["fields"]["priority"]["name"] == "High"

@responses.activate
def test_add_comment():
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue/OPS-42/comment", json={}, status=201)
    CLIENT.add_comment("OPS-42", "resolved")
    assert responses.calls[0].request.url.endswith("/OPS-42/comment")

@responses.activate
def test_transition_looks_up_id():
    responses.add(responses.GET, f"{BASE}/rest/api/3/issue/OPS-42/transitions",
                  json={"transitions": [{"id": "31", "name": "Done"}]}, status=200)
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue/OPS-42/transitions", json={}, status=204)
    CLIENT.transition("OPS-42", "Done")
    posted = json.loads(responses.calls[1].request.body)
    assert posted["transition"]["id"] == "31"
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `src/handler/jira.py`** (stdlib urllib, HTTP Basic)

```python
from __future__ import annotations
import base64
import json
import urllib.error
import urllib.request


class JiraError(RuntimeError):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self._base = base_url.rstrip("/")
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth = f"Basic {token}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"{self._base}{path}", data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            raise JiraError(f"{method} {path} -> {exc.code}: {exc.read().decode()}") from exc

    def create_issue(self, project_key: str, issue_type: str, summary: str,
                     description: dict, priority: str) -> str:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "description": description,
                "priority": {"name": priority},
            }
        }
        return self._request("POST", "/rest/api/3/issue", payload)["key"]

    def add_comment(self, issue_key: str, text: str) -> None:
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
            }
        }
        self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", payload)

    def transition(self, issue_key: str, transition_name: str) -> None:
        data = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        match = next((t for t in data.get("transitions", []) if t["name"] == transition_name), None)
        if match is None:
            return
        self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions",
                      {"transition": {"id": match["id"]}})
```

- [ ] **Step 4: Run tests** — PASS. `ruff check . && mypy`.

- [ ] **Step 5: Commit** — `git commit -m "feat: add Jira Cloud REST v3 client"`

---

### Task 4: DynamoDB state store

**Files:**
- Create: `src/handler/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces:
  - `state.StateStore(table_name: str)`.
  - `.put_if_absent(event_arn: str, issue_key: str) -> bool` — conditional put, returns `False` if the item already existed (dedup).
  - `.get_issue_key(event_arn: str) -> str | None`.
  - `.mark_closed(event_arn: str) -> None`.

- [ ] **Step 1: Write failing test** `tests/test_state.py` (moto)

```python
import boto3
import pytest
from moto import mock_aws
from handler.state import StateStore

TABLE = "health-jira"

@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "eventArn", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "eventArn", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield StateStore(TABLE)

def test_put_if_absent_first_wins(table):
    assert table.put_if_absent("arn1", "OPS-1") is True
    assert table.put_if_absent("arn1", "OPS-2") is False
    assert table.get_issue_key("arn1") == "OPS-1"

def test_get_missing_returns_none(table):
    assert table.get_issue_key("nope") is None

def test_mark_closed(table):
    table.put_if_absent("arn1", "OPS-1")
    table.mark_closed("arn1")
    # still resolvable, status updated
    assert table.get_issue_key("arn1") == "OPS-1"
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `src/handler/state.py`**

```python
from __future__ import annotations
import time
import boto3
from botocore.exceptions import ClientError

_TTL_SECONDS = 90 * 24 * 3600


class StateStore:
    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    def put_if_absent(self, event_arn: str, issue_key: str) -> bool:
        try:
            self._table.put_item(
                Item={
                    "eventArn": event_arn,
                    "issueKey": issue_key,
                    "status": "open",
                    "updatedAt": int(time.time()),
                    "ttl": int(time.time()) + _TTL_SECONDS,
                },
                ConditionExpression="attribute_not_exists(eventArn)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get_issue_key(self, event_arn: str) -> str | None:
        item = self._table.get_item(Key={"eventArn": event_arn}).get("Item")
        return item["issueKey"] if item else None

    def mark_closed(self, event_arn: str) -> None:
        self._table.update_item(
            Key={"eventArn": event_arn},
            UpdateExpression="SET #s = :c, updatedAt = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "closed", ":t": int(time.time())},
        )
```

- [ ] **Step 4: Run tests** — PASS. `ruff check . && mypy`.

- [ ] **Step 5: Commit** — `git commit -m "feat: add DynamoDB dedup and lifecycle state store"`

---

### Task 5: Handler orchestration

**Files:**
- Create: `src/handler/__init__.py` (empty), `src/handler/secrets.py`, `src/handler/handler.py`
- Test: `tests/test_handler.py`

**Interfaces:**
- Consumes: all prior modules.
- Produces:
  - `secrets.load_jira(secret_arn: str) -> dict` returns `{base_url, email, api_token}`.
  - `handler.lambda_handler(event: dict, context: object) -> dict` returns `{"status": "created|deduped|closed|ignored"}`.

- [ ] **Step 1: Write failing test** `tests/test_handler.py` (moto for ddb + secrets, responses for Jira)

```python
import json
import boto3
import pytest
import responses
from moto import mock_aws
from handler import handler

BASE = "https://example.atlassian.net"
TABLE = "health-jira"
SECRET = "jira-creds"

OPEN_EVENT = {
    "source": "aws.health", "account": "111122223333", "region": "us-east-1",
    "detail": {
        "eventArn": "arn:health:EC2/RETIRE/abc", "service": "EC2",
        "eventTypeCode": "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
        "statusCode": "open", "startTime": "s", "endTime": "e",
        "eventDescription": [{"latestDescription": "retire"}],
        "affectedEntities": [{"entityValue": "i-0abc"}],
    },
}

@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "eventArn", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "eventArn", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        arn = sm.create_secret(Name=SECRET, SecretString=json.dumps(
            {"base_url": BASE, "email": "me@x.com", "api_token": "t"}))["ARN"]
        monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
        monkeypatch.setenv("JIRA_ISSUE_TYPE", "Task")
        monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
        monkeypatch.setenv("PRIORITY_MAP_JSON", json.dumps({"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"}))
        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("SECRET_ARN", arn)
        monkeypatch.setenv("DONE_TRANSITION", "Done")
        yield

@responses.activate
def test_open_event_creates_ticket(env):
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue", json={"key": "OPS-1"}, status=201)
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "created"

@responses.activate
def test_duplicate_event_deduped(env):
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue", json={"key": "OPS-1"}, status=201)
    handler.lambda_handler(OPEN_EVENT, None)
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "deduped"

@responses.activate
def test_closed_event_transitions(env):
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue", json={"key": "OPS-1"}, status=201)
    handler.lambda_handler(OPEN_EVENT, None)
    closed = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "statusCode": "closed"}}
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue/OPS-1/comment", json={}, status=201)
    responses.add(responses.GET, f"{BASE}/rest/api/3/issue/OPS-1/transitions",
                  json={"transitions": [{"id": "31", "name": "Done"}]}, status=200)
    responses.add(responses.POST, f"{BASE}/rest/api/3/issue/OPS-1/transitions", json={}, status=204)
    assert handler.lambda_handler(closed, None)["status"] == "closed"

def test_non_ec2_ignored(env):
    raw = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "service": "RDS"}}
    assert handler.lambda_handler(raw, None)["status"] == "ignored"
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `src/handler/secrets.py`**

```python
from __future__ import annotations
import json
import boto3


def load_jira(secret_arn: str) -> dict:
    client = boto3.client("secretsmanager")
    raw = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    return json.loads(raw)
```

- [ ] **Step 4: Implement `src/handler/handler.py`**

```python
from __future__ import annotations
import json
import logging

from . import config, enrich, events, secrets
from .jira import JiraClient
from .state import StateStore

log = logging.getLogger()
log.setLevel(logging.INFO)


def _log(status: str, event_arn: str, **extra: object) -> None:
    log.info(json.dumps({"status": status, "eventArn": event_arn, **extra}))


def lambda_handler(event: dict, context: object) -> dict:
    ev = events.parse(event)
    if ev is None:
        _log("ignored", event.get("detail", {}).get("eventArn", ""))
        return {"status": "ignored"}

    cfg = config.load()
    creds = secrets.load_jira(cfg.secret_arn)
    jira = JiraClient(creds["base_url"], creds["email"], creds["api_token"])
    store = StateStore(cfg.table_name)

    if ev.is_closed:
        issue_key = store.get_issue_key(ev.event_arn)
        if issue_key is None:
            _log("ignored", ev.event_arn, reason="closed-untracked")
            return {"status": "ignored"}
        jira.add_comment(issue_key, "AWS Health event resolved. Closing.")
        jira.transition(issue_key, cfg.done_transition)
        store.mark_closed(ev.event_arn)
        _log("closed", ev.event_arn, issueKey=issue_key)
        return {"status": "closed"}

    existing = store.get_issue_key(ev.event_arn)
    if existing is not None:
        _log("deduped", ev.event_arn, issueKey=existing)
        return {"status": "deduped"}

    issue_key = jira.create_issue(
        cfg.project_key, cfg.issue_type,
        enrich.summary(ev), enrich.description(ev), enrich.priority(cfg, ev),
    )
    if not store.put_if_absent(ev.event_arn, issue_key):
        _log("deduped", ev.event_arn, issueKey=issue_key, reason="race")
        return {"status": "deduped"}
    _log("created", ev.event_arn, issueKey=issue_key)
    return {"status": "created"}
```

- [ ] **Step 5: Run tests** — `pytest -v` → all PASS. `ruff check . && mypy`.

- [ ] **Step 6: Commit** — `git commit -m "feat: add lambda handler orchestrating create, dedup, and auto-close"`

---

### Task 6: Terraform infrastructure

**Files:**
- Create: `terraform/versions.tf`, `terraform/backend.tf`, `terraform/variables.tf`, `terraform/main.tf`, `terraform/outputs.tf`, `terraform/terraform.tfvars.example`

**Interfaces:**
- Consumes: `dist/handler.zip` from `make package`.
- Produces: deployed EventBridge rule, Lambda, IAM role, DynamoDB table, SQS DLQ, Secrets Manager secret reference. This is the delegated-admin (central ops) account deploy.

- [ ] **Step 1: `terraform/versions.tf`** (verify latest provider at implementation)

```hcl
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.57"
    }
  }
}
```

- [ ] **Step 2: `terraform/backend.tf`** (S3 native lockfile, no DynamoDB)

```hcl
terraform {
  backend "s3" {
    # bucket, key, region supplied via -backend-config at init
    use_lockfile = true
    encrypt      = true
  }
}
```

- [ ] **Step 3: `terraform/variables.tf`**

```hcl
variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "aws-health-jira"
}

variable "jira_project_key" {
  type = string
}

variable "jira_issue_type" {
  type    = string
  default = "Task"
}

variable "default_priority" {
  type    = string
  default = "Low"
}

variable "priority_map" {
  type    = map(string)
  default = { AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED = "High" }
}

variable "done_transition" {
  type    = string
  default = "Done"
}

variable "jira_secret_arn" {
  description = "ARN of an existing Secrets Manager secret holding {base_url,email,api_token}"
  type        = string
}

variable "event_type_categories" {
  type    = list(string)
  default = ["scheduledChange"]
}
```

- [ ] **Step 4: `terraform/main.tf`**

```hcl
provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

# --- DynamoDB app state ---
resource "aws_dynamodb_table" "state" {
  name         = "${var.name_prefix}-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "eventArn"

  attribute {
    name = "eventArn"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# --- DLQ ---
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# --- IAM ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
  }
  statement {
    sid       = "Ddb"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.state.arn]
  }
  statement {
    sid       = "Secret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.jira_secret_arn]
  }
  statement {
    sid       = "Dlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name_prefix}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# --- Lambda ---
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}"
  retention_in_days = 90
}

resource "aws_lambda_function" "handler" {
  function_name    = var.name_prefix
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = "handler.handler.lambda_handler"
  filename         = "${path.module}/../dist/handler.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/handler.zip")
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      JIRA_PROJECT_KEY = var.jira_project_key
      JIRA_ISSUE_TYPE  = var.jira_issue_type
      DEFAULT_PRIORITY = var.default_priority
      PRIORITY_MAP_JSON = jsonencode(var.priority_map)
      TABLE_NAME       = aws_dynamodb_table.state.name
      SECRET_ARN       = var.jira_secret_arn
      DONE_TRANSITION  = var.done_transition
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# --- EventBridge ---
resource "aws_cloudwatch_event_rule" "health" {
  name = "${var.name_prefix}-rule"
  event_pattern = jsonencode({
    source      = ["aws.health"]
    detail-type = ["AWS Health Event"]
    detail = {
      service           = ["EC2"]
      eventTypeCategory = var.event_type_categories
    }
  })
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.health.name
  arn  = aws_lambda_function.handler.arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.handler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.health.arn
}

resource "aws_sqs_queue_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.dlq.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.health.arn } }
    }]
  })
}
```

- [ ] **Step 5: `terraform/outputs.tf`**

```hcl
output "lambda_name" {
  value = aws_lambda_function.handler.function_name
}

output "rule_name" {
  value = aws_cloudwatch_event_rule.health.name
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.id
}

output "table_name" {
  value = aws_dynamodb_table.state.name
}
```

- [ ] **Step 6: `terraform/terraform.tfvars.example`**

```hcl
region           = "us-east-1"
jira_project_key = "OPS"
jira_secret_arn  = "arn:aws:secretsmanager:us-east-1:111122223333:secret:jira-creds-XXXX"
priority_map = {
  AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED = "High"
}
```

- [ ] **Step 7: Validate** — `make package` then `terraform -chdir=terraform init -backend=false && terraform -chdir=terraform validate && terraform -chdir=terraform fmt -check && tflint --chdir=terraform && checkov -d terraform`. Fix any findings.

- [ ] **Step 8: Commit** — `git commit -m "feat: add terraform for eventbridge, lambda, dynamodb, dlq, iam"`

---

### Task 7: Docs and delegated-admin note

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Document org-wide enablement** in README: the one-time
  `aws organizations register-delegated-administrator --account-id <CENTRAL> --service-principal health.amazonaws.com`
  step (run once in the management account, outside Terraform since it is an
  org-management action), plus how AWS Health org events reach the central bus.

- [ ] **Step 2: Document deploy flow:** create the Jira secret, `make package`,
  `terraform init -backend-config=...`, `terraform apply -var-file=terraform.tfvars`.

- [ ] **Step 3: Document the Jira secret JSON shape** `{base_url, email, api_token}`
  and required Jira project permissions (create issue, transition, comment).

- [ ] **Step 4: Commit** — `git commit -m "docs: add deployment and org-delegation guide"`

---

## Self-Review Notes

- **Spec coverage:** EventBridge rule (T6), org-delegation (T7 + README), Lambda modules (T1-T5), DynamoDB dedup+lifecycle (T4, T5), B1 enrichment (T2), priority map (T2, T6), Secrets Manager (T5, T6), DLQ (T6), S3 native-lock backend (T6), lint/CI stack (T0), tests (T1-T5). All spec sections mapped.
- **Type consistency:** `HealthEvent`, `Config` fields, `JiraClient` methods, `StateStore` methods used identically across tasks. `enrich.priority/summary/description` signatures match handler call site. `secrets.load_jira` returns `{base_url,email,api_token}` consumed by `JiraClient`.
- **No placeholders:** all steps contain runnable code or exact commands. Version pins for pre-commit/Docker/provider carry an explicit "verify latest stable at implementation" instruction per repo policy.
