# Cambium verification entry points.
#
# One entry point, used by humans and by CI alike, so the two cannot drift.
# `make ci` is exactly what .github/workflows/verify.yml runs.
#
# The three cache states in `test-cache-states` are not ceremony: the repository
# snapshot defect that shipped in the first release only appeared when the
# bytecode cache changed between runs, so a single pass would not have caught it.

PYTHON ?= python3
PROFILE ?= profiles/examples/agent-atlas

.PHONY: help check test ci clean-cache test-cache-states

help:
	@echo "make check              deterministic checks only (seconds)"
	@echo "make test               full unit test suite"
	@echo "make ci                 what CI runs: check + all three cache states"
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
	$(PYTHON) -m unittest discover -s Tools/tests -p "test_*.py"

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

ci: check test-cache-states
