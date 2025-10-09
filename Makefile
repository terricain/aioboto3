
lint:
	uv run python -m flake8 aioboto3 tests

test:
	uv run pytest
