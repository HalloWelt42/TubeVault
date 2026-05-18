.PHONY: test test-cov install-dev sync

# Synct geänderte app/-Dateien in den laufenden Container (kein Rebuild).
# Nötig damit Tests frischen Code treffen ohne docker compose build.
# Wir löschen erst die Zielordner damit docker cp KEIN stale merge macht —
# sonst überschreibt docker cp nur existierende Dateien, neue werden übersehen
# wenn die Cache-Layer komisch sind.
sync:
	docker exec tubevault-backend sh -c "find /app/app -name __pycache__ -exec rm -rf {} + 2>/dev/null; true"
	cd .. && docker cp backend/app/. tubevault-backend:/app/app/
	cd .. && docker cp backend/pytest.ini tubevault-backend:/app/pytest.ini

# Tests im laufenden Backend-Container (schnell, kein Rebuild).
# Kopiert app/ + tests/ + pytest.ini live rein und führt pytest aus.
# Hinweis: 'docker cp dir container:/dest' → merged/ersetzt, deshalb erst rm.
test: sync
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v"

test-cov: sync
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	docker exec tubevault-backend sh -c "cd /app && python -m pytest tests/ -v --cov=app --cov-report=term-missing"

install-dev:
	docker exec tubevault-backend pip install -q -r /app/requirements-dev.txt

# Ein einzelner Test:  make test-one T=tests/test_cooldown.py::test_reload_reads_setting
test-one: sync
	docker exec tubevault-backend rm -rf /app/tests
	cd .. && docker cp backend/tests tubevault-backend:/app/tests
	docker exec tubevault-backend sh -c "cd /app && python -m pytest $(T) -v"
