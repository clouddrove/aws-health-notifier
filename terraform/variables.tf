variable "region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix applied to all resource names."
  type        = string
  default     = "aws-health-notifier"
}

variable "notifier" {
  description = "Notifier backend that receives events (jira today)."
  type        = string
  default     = "jira"
}

variable "jira_project_key" {
  description = "Jira project key that tickets are created in."
  type        = string
}

variable "jira_issue_type" {
  description = "Jira issue type name."
  type        = string
  default     = "Task"
}

variable "default_priority" {
  description = "Priority applied when no mapping matches the event type."
  type        = string
  default     = "Low"
}

variable "priority_map" {
  description = "Map of AWS Health eventTypeCode to Jira priority name."
  type        = map(string)
  default     = { AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED = "High" }
}

variable "done_transition" {
  description = "Jira transition name used to close a ticket when the event resolves."
  type        = string
  default     = "Done"
}

variable "jira_secret_arn" {
  description = "ARN of an existing Secrets Manager secret holding {base_url,email,api_token}."
  type        = string
}

variable "event_type_categories" {
  description = "AWS Health eventTypeCategory values to capture."
  type        = list(string)
  default     = ["scheduledChange"]
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 90
}
