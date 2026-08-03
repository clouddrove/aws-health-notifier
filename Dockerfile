FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git zip curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    ruff mypy pytest "moto[dynamodb,secretsmanager]" \
    boto3 "boto3-stubs[dynamodb,secretsmanager]" checkov

# tflint
RUN curl -sSL https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

WORKDIR /work
