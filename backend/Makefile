.PHONY: test test-cov install-dev

# Tests im laufenden Backend-Container (schnell, kein Rebuild).
# Kopiert tests/ + pytest.ini live rein und führt pytest aus.
test:
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v"

test-cov:
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v --cov=app --cov-report=term-missing"

install-dev:
	docker exec tubevault-backend pip install -q -r /app/requirements-dev.txt

# Ein einzelner Test:  make test-one T=tests/test_cooldown.py::test_reload_reads_setting
test-one:
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest $(T) -v"
