.PHONY: clean clean-test clean-pyc clean-build docs help
.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

ifndef PYTHON_VERSION
PYTHON_VERSION			:= python310
endif

ifndef BUCKET
BUCKET					:= files.compose-x.io
endif

ifndef PYTHON_PACKAGE
PYTHON_PACKAGE			:= ssl_expiry_monitor
endif

ifndef S3_PATH
S3_PATH					:= $(shell echo s3://$(BUCKET)/$(PYTHON_PACKAGE)/$(PYTHON_PACKAGE)-$$(date +%Y%m%d%H%M%S).zip)
endif

BROWSER := python -c "$$BROWSER_PYSCRIPT"

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: docker-clean clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -rf {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

lint: ## check style with flake8
	flake8 ssl_expiry_monitor tests

test: ## run tests quickly with the default Python
	pytest -svx tests/

test-all: ## run tests on every Python version with tox
	tox

coverage: ## check code coverage quickly with the default Python
	coverage run --source ssl_expiry_monitor -m pytest
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html

docs: ## generate Sphinx HTML documentation, including API docs
	rm -f docs/ssl_expiry_monitor.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ ssl_expiry_monitor
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs ## compile the docs watching for changes
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

conform	: ## Conform to a standard of coding syntax
	isort --profile black ssl_expiry_monitor
	black ssl_expiry_monitor tests
	find ssl_expiry_monitor -name "*.json" -type f  -exec sed -i '1s/^\xEF\xBB\xBF//' {} +

docker-clean:
			docker run --rm -v $(PWD):/app public.ecr.aws/amazonlinux/amazonlinux:2 rm -rf /app/python

python310	: docker-clean
			test -d layer && rm -rf layer || mkdir layer
			docker run \
			--rm -v $(PWD):/app --entrypoint /bin/bash \
			--workdir /app \
			public.ecr.aws/lambda/python:3.10 \
			-c "pip install pip -U; pip install /app/dist/*.whl -t /app/python"

dist:		clean ## builds source and wheel package
			poetry build

package:	dist $(PYTHON_VERSION)

zip:		package
			docker run --rm -v $(PWD):/app public.ecr.aws/amazonlinux/amazonlinux:2 chown 1000:1000 -R /app/python
			zip -q -r9 layer.zip python

upload-zip-s3: zip
			echo $(S3_PATH)
			aws s3 cp --sse AES256 --acl public-read --storage-class STANDARD_IA --no-progress layer.zip $(S3_PATH)


sar-template: upload-zip-s3
			S3_LAYER_UPLOAD_PATH=$(S3_PATH) envsubst '$$S3_LAYER_UPLOAD_PATH' < .install/layer-macro-sar.yaml > ssl-expiry-monitor-sar.yaml
