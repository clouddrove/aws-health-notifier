# Opt-in cross-account read role for instance tag enrichment.
# Deployed org-wide via a service-managed StackSet only when enrich_tags is set.
resource "aws_cloudformation_stack_set" "describe" {
  count            = var.enrich_tags ? 1 : 0
  name             = "${var.name_prefix}-describe"
  description      = "Read-only DescribeInstances role for aws-health-notifier tag enrichment."
  permission_model = "SERVICE_MANAGED"
  capabilities     = ["CAPABILITY_NAMED_IAM"]

  auto_deployment {
    enabled                          = true
    retain_stacks_on_account_removal = false
  }

  template_body = jsonencode({
    Resources = {
      DescribeRole = {
        Type = "AWS::IAM::Role"
        Properties = {
          RoleName = var.describe_role_name
          AssumeRolePolicyDocument = {
            Version = "2012-10-17"
            Statement = [{
              Effect    = "Allow"
              Principal = { AWS = aws_iam_role.lambda.arn }
              Action    = "sts:AssumeRole"
            }]
          }
          Policies = [{
            PolicyName = "describe-instances"
            PolicyDocument = {
              Version = "2012-10-17"
              Statement = [{
                Effect   = "Allow"
                Action   = "ec2:DescribeInstances"
                Resource = "*"
              }]
            }
          }]
        }
      }
    }
  })
}

resource "aws_cloudformation_stack_set_instance" "describe" {
  count          = var.enrich_tags ? 1 : 0
  stack_set_name = aws_cloudformation_stack_set.describe[0].name
  region         = var.region

  deployment_targets {
    organizational_unit_ids = [var.org_root_id]
  }
}
