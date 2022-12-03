
lint:
	poetry run python -m flake8 aioboto3 tests

test:
	poetry run pytest
