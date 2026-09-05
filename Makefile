# Cambium verification entry points.
#
# `make ci` is the full verification entry point for humans.  Pull-request CI
# uses .github/scripts/ci_impact.py to select the smallest fail-closed proof
# set. Pushes to main and manual runs retain the complete verification suite.
# `make ci-exhaustive` retains the slower historical cache-state sweep for
# explicit deep verification.
#
# The focused cache contract runs in required CI. The three cache states in
# `test-cache-states` remain available for reproducing the historical repository
# snapshot defect without multiplying every required test run.

PYTHON ?= python3
PROFILE ?= profiles/examples/agent-atlas
TEST_FILES ?=
TEST_JOBS ?= 4

.PHONY: help check test test-selected fast integration e2e slow full test-cache-contract clean-cache test-cache-states ci ci-exhaustive

help:
	@echo "make check              deterministic checks only (seconds)"
	@echo "make test               alias of the catalog-owned full suite"
	@echo "make test-selected      exact TEST_FILES selected by the CI impact plan"
	@echo "make fast               catalog-owned unit + contract tests"
	@echo "make integration        adjacent Tool/runtime integration tests"
	@echo "make e2e                representative complete lifecycle tests"
	@echo "make slow               security, concurrency, and recovery tests"
	@echo "make full               all current catalog-owned test levels"
	@echo "make test-cache-contract focused cache/snapshot contract test"
	@echo "make ci                 required checks + full catalog-owned suite"
	@echo "make ci-exhaustive      check + cold/warm/post-touch full suites"
	@echo "make test-cache-states  cold/warm/post-touch full suites"
	@echo "make clean-cache        remove __pycache__ trees"
	@echo ""
	@echo "PYTHON=$(PYTHON)  PROFILE=$(PROFILE)  TEST_JOBS=$(TEST_JOBS)"

# Distribution verification runs repository-engineering preflights alongside
# adopter Gate producers. stamp_cards --check covers curated Card currentness
# and the Card/Read Set machine contracts; check_kernel_size independently
# covers the Tool-owned Kernel leaf-size policy. Neither is a Kernel Gate.
#
# compile_cli_contract --check covers Tools/compiled/cli-contract.yaml, the
# compiled statement of every tool's argparse calling contract plus the closed
# agent-interface capability policy.  Tool, argument, exposure, workspace, and
# path-constraint closure therefore fail before any host projection is served.
# It is placed here rather than in the K00/12 Stable Gate ID Registry on
# purpose: run_gates needs a selected profile before it can start, and this
# artifact depends on no profile at all, so a registry row for it could never
# be swept.
#
# metadata_execution_contract --check binds live Kernel metadata authority to
# the installed writer/consumer/producer capability registry.  It runs here
# because every metadata writer and typed extension Gate consumes that same
# profile-independent compiled authority boundary.
#
# render_interface_projection --check covers every agent-facing form projected
# from that contract (today Tools/compiled/mcp-tools.json).  It runs directly
# after its own upstream, and stays out of the registry for the same reason.
#
# render_host_configs --check covers the five host configuration products under
# Tools/compiled/host-configs/, which carry the sha256 of that projection, so
# it runs directly after it and stays out of the registry for the same reason
# again.  Those products are templates for an adopter's corpus repository; this
# repository registers no MCP server with itself.
check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) .github/scripts/ci_impact.py validate --root .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_links.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_kernel_size.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/stamp_cards.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/metadata_execution_contract.py --root . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m Tools.governance.profile.profile_schema_projection --root . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/compile_cli_contract.py . --check --projection-target source-distribution
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/render_interface_projection.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/render_host_configs.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_moc.py .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_profile.py $(PROFILE)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/check_repository_structure.py . --profile-manifest "$(PROFILE)/profile.toml"
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/generate_tool_catalog.py . --check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/generate_test_catalog.py . --check

test: full

test-selected:
	@test -n "$(TEST_FILES)" || (echo "TEST_FILES is required" && exit 1)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) .github/scripts/ci_impact.py run-tests --root . --tests "$(TEST_FILES)"

fast:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/run_tests.py fast --root . --python "$(PYTHON)" --jobs "$(TEST_JOBS)"

integration:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/run_tests.py integration --root . --python "$(PYTHON)" --jobs "$(TEST_JOBS)"

e2e:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/run_tests.py e2e --root . --python "$(PYTHON)" --jobs "$(TEST_JOBS)"

slow:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/run_tests.py slow --root . --python "$(PYTHON)" --jobs "$(TEST_JOBS)"

full:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) Tools/run_tests.py full --root . --python "$(PYTHON)" --jobs "$(TEST_JOBS)"

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

ci: check full

ci-exhaustive: check test-cache-states
