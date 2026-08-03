provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.name_prefix
      ManagedBy = "terraform"
    }
  }
}

# DynamoDB application state (dedup + lifecycle)
resource "aws_dynamodb_table" "state" {
  # checkov:skip=CKV_AWS_119: table holds only eventArn to issueKey mapping, no sensitive data; SSE with the AWS-managed key is sufficient and avoids KMS cost.
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

# Dead letter queue for failed async invocations
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# IAM role and least-privilege policy
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
    sid     = "Logs"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      aws_cloudwatch_log_group.lambda.arn,
      "${aws_cloudwatch_log_group.lambda.arn}:*",
    ]
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
  statement {
    sid       = "Xray"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name_prefix}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# Lambda
# Terraform builds the deployment zip from src/ so the handler/ package dir is
# preserved (entrypoint handler.handler.lambda_handler). No prebuilt zip needed.
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../dist/handler.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  # checkov:skip=CKV_AWS_158: logs carry only status, eventArn, and issueKey, no secrets; AWS-managed encryption is sufficient.
  # checkov:skip=CKV_AWS_338: retention is set via var (90 days default) to balance cost against audit need.
  name              = "/aws/lambda/${var.name_prefix}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "handler" {
  # checkov:skip=CKV_AWS_117: function calls public Jira and AWS APIs only; a VPC would add NAT cost with no security benefit.
  # checkov:skip=CKV_AWS_173: environment holds config and the secret ARN only, never the token; AWS-managed encryption at rest is sufficient.
  # checkov:skip=CKV_AWS_272: code signing is out of scope for this internal event handler.
  function_name    = var.name_prefix
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = "handler.handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30
  memory_size      = 256

  reserved_concurrent_executions = 5

  environment {
    variables = {
      NOTIFIER          = var.notifier
      JIRA_PROJECT_KEY  = var.jira_project_key
      JIRA_ISSUE_TYPE   = var.jira_issue_type
      DEFAULT_PRIORITY  = var.default_priority
      PRIORITY_MAP_JSON = jsonencode(var.priority_map)
      TABLE_NAME        = aws_dynamodb_table.state.name
      SECRET_ARN        = var.jira_secret_arn
      DONE_TRANSITION   = var.done_transition
    }
  }

  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# EventBridge rule for org-wide AWS Health EC2 events
resource "aws_cloudwatch_event_rule" "health" {
  name        = "${var.name_prefix}-rule"
  description = "Capture AWS Health EC2 scheduled-change events."
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
