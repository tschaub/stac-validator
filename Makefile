help:			## Show this help
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

install:		## Install using pip
	pip install .

install-edit:		## Install using pip in edit mode
	pip install --editable .["test"]

code-check:		## Check and format code using pre-commit
	pre-commit install
	pre-commit autoupdate
	pre-commit run --all-files

test:			## Run the tests
	pytest --verbose
	pytest --mypy stac_validator

build:			## Build a Docker container
	docker build -t stac_validator:2.0.0 .

build-libraries: # Build the libraries for layers. Used internally
	cd cdk-deployment/lambda-libraries && \
	docker build -f "Dockerfile" -t lambdalayer:latest .
	docker run -d -it --name lambdalayer lambdalayer:latest
	docker cp lambdalayer:libraries.zip ./cdk-deployment/lambda
	docker stop lambdalayer
	docker rm lambdalayer
	docker rmi lambdalayer
	zip -r stac_validator.zip ./stac_validator/
	cp -r stac_validator.zip cdk-deployment/lambda

build-cdk: 		## Build the libraries in preperation for CDK deployment
	make build-libraries

build-tox:		## Test stac_validator on multiple Python versions
	docker build -f Dockerfile-tox -t stac_tox .

run:			## Run the Docker Container and enter into bash
	docker run -it --entrypoint /bin/bash stac_validator:2.0.0
