.PHONY: venv test test-cov test-one

# Tests laufen in einer lokalen Umgebung (backend/.venv) gegen eine
# Wegwerf-Datenbank im Temp-Ordner - nie im laufenden Container und nie
# gegen echte Daten.
PY := .venv/bin/python

venv:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -r requirements.txt -r requirements-dev.txt

test:
	$(PY) -m pytest tests/ -q

test-cov:
	$(PY) -m pytest tests/ -q --cov=app --cov-report=term-missing

# Ein einzelner Test:  make test-one T=tests/test_cooldown.py::test_reload_reads_setting
test-one:
	$(PY) -m pytest $(T) -v
