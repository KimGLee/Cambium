# Cambium verification entry points.
#
# `make ci` is the required entry point for humans and CI alike, so the two
# cannot drift. `make ci-exhaustive` retains the slower historical cache-state
# sweep for explicit deep verification.
#
# The focused cache contract runs in required CI. The three cache states in
# `test-cache-states` remain available for reproducing the historical repository
# snapshot defect without multiplying every required test run.

PYTHON ?= python3
PROFILE ?= profiles/examples/agent-atlas

.PHONY: help check test test-cache-contract clean-cache test-cache-states ci ci-exhaustive

help:
	@echo "make check              deterministic checks only (seconds)"
	@echo "make test               full unit test suite (single pass, no bytecode writes)"
	@echo "make test-cache-contract focused cache/snapshot contract test"
	@echo "make ci                 required CI: check + one full suite"
	@echo "make ci-exhaustive      check + cold/warm/post-touch full suites"
	@echo "make test-cache-states  cold/warm/post-touch full suites"
	@echo "make clean-cache        remove __pycache__ trees"
	@echo ""
	@echo "PYTHON=$(PYTHON)  PROFILE=$(PROFILE)"

# Every gate that decides whether the distribution is internally consistent.
# stamp_cards --check covers Card synchronisation, the Card/Read Set skeleton
# contract, Card gate commands against each tool's argparse contract, Read Set
# boundary coverage of every leaf, the leaf size budget, and the Stable Gate ID
# Registry producer table.
check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_links.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/stamp_cards.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_moc.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_profile.py $(PROFILE)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -c "import sys; sys.path.insert(0, 'Tools'); import check_batch_close as c; r = c._structural_check('.', {'queue': {'selected_profile_manifest': '$(PROFILE)/profile.md'}}); print('structural_errors =', len(r['errors'])); sys.exit(1 if r['errors'] else 0)"

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s Tools/tests -p "test_*.py"

test-cache-contract:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s Tools/tests -p "test_runtime_safety.py" -k test_snapshot_excludes_import_cache_but_tracks_source_bytes

clean-cache:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

# Cold, warm, and post-touch. Deliberately without PYTHONDONTWRITEBYTECODE:
# the suite must pass while the interpreter is writing bytecode into the same
# tree the gates measure.
test-cache-states: clean-cache
	@echo "--- cold cache ---"
	$(PYTHON) -m unittest discover -s Tools/tests -p "test_*.py"
	@echo "--- warm cache ---"
	$(PYTHON) -m unittest discover -s Tools/tests -p "test_*.py"
	@echo "--- after touching the tools ---"
	touch Tools/*.py && $(PYTHON) -m unittest discover -s Tools/tests -p "test_*.py"

ci: check test

ci-exhaustive: check test-cache-states
