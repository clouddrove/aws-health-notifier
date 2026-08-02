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
	rm -rf build dist && mkdir -p dist build
	cp -r src/handler/* build/
	cd build && zip -r ../dist/handler.zip . -x '*.pyc' '__pycache__/*'

tf-validate:
	terraform -chdir=terraform fmt -check
	tflint --chdir=terraform
	checkov -d terraform --quiet

plan:
	terraform -chdir=terraform plan
