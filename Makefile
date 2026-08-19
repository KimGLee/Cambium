# Cambium verification entry points.
#
# `make ci` is the full required entry point for humans.  Required CI invokes
# three fixed `ci-*` targets whose checked partition is exactly that same suite.
# `make ci-exhaustive` retains the slower historical cache-state sweep for
# explicit deep verification.
#
# The focused cache contract runs in required CI. The three cache states in
# `test-cache-states` remain available for reproducing the historical repository
# snapshot defect without multiplying every required test run.

PYTHON ?= python3
PROFILE ?= profiles/examples/agent-atlas
TEST_PATTERN ?= test_*.py

.PHONY: help check check-test-shards test test-cache-contract clean-cache test-cache-states ci ci-a-m ci-n-r ci-s-z ci-exhaustive

help:
	@echo "make check              deterministic checks only (seconds)"
	@echo "make test               unit tests selected by TEST_PATTERN (default: full suite)"
	@echo "make test-cache-contract focused cache/snapshot contract test"
	@echo "make ci                 required checks + full unit test suite"
	@echo "make ci-exhaustive      check + cold/warm/post-touch full suites"
	@echo "make test-cache-states  cold/warm/post-touch full suites"
	@echo "make clean-cache        remove __pycache__ trees"
	@echo ""
	@echo "PYTHON=$(PYTHON)  PROFILE=$(PROFILE)  TEST_PATTERN=$(TEST_PATTERN)"

# Every gate that decides whether the distribution is internally consistent.
# stamp_cards --check covers Card synchronisation, the Card/Read Set skeleton
# contract, Card gate commands against each tool's argparse contract, Read Set
# boundary coverage of every leaf, the leaf size budget, and the Stable Gate ID
# Registry producer table.
#
# compile_cli_contract --check covers Tools/compiled/cli-contract.yaml, the
# compiled statement of every tool's argparse calling contract.  It is placed
# here rather than in the K00/12 Stable Gate ID Registry on purpose: run_gates
# needs a selected profile before it can start, and this artifact depends on
# no profile at all, so a registry row for it could never be swept.
#
# render_interface_projection --check covers every agent-facing form projected
# from that contract (today Tools/compiled/mcp-tools.json).  It runs directly
# after its own upstream, and stays out of the registry for the same reason.
check: check-test-shards
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_links.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/stamp_cards.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/compile_cli_contract.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/render_interface_projection.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_moc.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_profile.py $(PROFILE)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -c "import sys; sys.path.insert(0, 'Tools'); import check_batch_close as c; r = c._structural_check('.', {'queue': {'selected_profile_manifest': '$(PROFILE)/profile.md'}}); print('structural_errors =', len(r['errors'])); sys.exit(1 if r['errors'] else 0)"

# Required CI shards the suite by the first letter after ``test_``.  This
# check prevents a future test file from silently falling outside that
# partition while keeping ``make test`` a full-suite command by default.
check-test-shards:
	@all="$$(find Tools/tests -type f -name 'test_*.py' | LC_ALL=C sort)"; \
	a_m="$$(find Tools/tests -type f -name 'test_[a-m]*.py' | LC_ALL=C sort)"; \
	n_r="$$(find Tools/tests -type f -name 'test_[n-r]*.py' | LC_ALL=C sort)"; \
	s_z="$$(find Tools/tests -type f -name 'test_[s-z]*.py' | LC_ALL=C sort)"; \
	sharded="$$(printf '%s\n%s\n%s\n' "$$a_m" "$$n_r" "$$s_z" | sed '/^$$/d' | LC_ALL=C sort)"; \
	if test -z "$$a_m" || test -z "$$n_r" || test -z "$$s_z" || test "$$all" != "$$sharded"; then \
		echo "CI test shard partition does not cover every Tools/tests/test_*.py file exactly once"; \
		exit 1; \
	fi

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s Tools/tests -p "$(TEST_PATTERN)"

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

ci-a-m:
	$(MAKE) ci TEST_PATTERN='test_[a-m]*.py'

ci-n-r:
	$(MAKE) ci TEST_PATTERN='test_[n-r]*.py'

ci-s-z:
	$(MAKE) ci TEST_PATTERN='test_[s-z]*.py'

ci-exhaustive: check test-cache-states
