.PHONY: test test-cov install-dev

# Tests im laufenden Backend-Container (schnell, kein Rebuild).
# Kopiert tests/ + pytest.ini live rein und führt pytest aus.
# Hinweis: 'docker cp dir container:/dest' → merged/ersetzt, deshalb erst rm.
test:
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v"

test-cov:
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v --cov=app --cov-report=term-missing"

install-dev:
	docker exec tubevault-backend pip install -q -r /app/requirements-dev.txt

# Ein einzelner Test:  make test-one T=tests/test_cooldown.py::test_reload_reads_setting
test-one:
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini
	docker exec tubevault-backend sh -c "cd /app && python -m pytest $(T) -v"
