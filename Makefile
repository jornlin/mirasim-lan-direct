PY ?= python3
export PYTHONPATH := src

.PHONY: test compile check help

help:
	@echo "make test     run the unit tests"
	@echo "make compile  byte-compile the package"
	@echo "make check    compile + tests"

test:
	$(PY) -m unittest discover -s tests -v

compile:
	$(PY) -m compileall -q src

check: compile test