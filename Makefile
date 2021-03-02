
lint:
	pipenv run python3 -m flake8 aioboto3 tests

test:
	pipenv run -Wd -m pytest
