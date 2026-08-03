output "lambda_name" {
  description = "Name of the handler Lambda function."
  value       = aws_lambda_function.handler.function_name
}

output "rule_name" {
  description = "Name of the EventBridge rule."
  value       = aws_cloudwatch_event_rule.health.name
}

output "dlq_url" {
  description = "URL of the dead letter queue."
  value       = aws_sqs_queue.dlq.id
}

output "table_name" {
  description = "Name of the DynamoDB state table."
  value       = aws_dynamodb_table.state.name
}
