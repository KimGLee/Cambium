"""One-off external timing observer; not a test or acceptance owner.

The measured checkout and original selector, fixtures and producers remain
unchanged. Completed scope emission is timestamped with 0.1s polling; parent
and child durations must not be added together. The 360s marker never cancels
work. The original runner gets an independent 1800s safety deadline.
"""

import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != "6b7ce7c13710e2f9b14021188c87bb7d38046967":
        raise SystemExit("unexpected measured revision")
    report = output / "test-costs.json"
    progress = report.with_suffix(".progress") / "test_required_queue_e2e.jsonl"
    started = time.monotonic()
    started_epoch = time.time()
    command = ["make", "test-selected", "PYTHON=python",
               "TEST_FILES=test_required_queue_e2e.py", "TEST_REPORT=" + str(report),
               "TEST_DEADLINE=" + str(started_epoch + 1800)]
    metadata = {
        "purpose": "diagnosis only; never required-CI acceptance",
        "revision": revision, "controller_revision": os.environ.get("GITHUB_SHA"),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "started_epoch": started_epoch,
        "command": command, "formal_ci_target_seconds": 300,
        "formal_ci_limit_seconds": 360, "safety_seconds": 1800,
        "python": sys.version, "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "observation_resolution_seconds": 0.1,
        "ci": {key: os.environ.get(key) for key in (
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "ImageOS", "ImageVersion", "RUNNER_ARCH")},
    }
    (output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    finished = threading.Event()

    def observe():
        offset, last, marked = 0, [], False
        with (output / "observed-progress.jsonl").open("x") as sink:
            while True:
                if progress.exists():
                    with progress.open() as source:
                        source.seek(offset)
                        while True:
                            position = source.tell()
                            line = source.readline()
                            if not line or not line.endswith("\n"):
                                source.seek(position)
                                break
                            row = json.loads(line)
                            observed = {"observed_elapsed": time.monotonic() - started,
                                        "scope": row}
                            sink.write(json.dumps(observed) + "\n")
                            last = (last + [observed])[-12:]
                        offset = source.tell()
                    sink.flush()
                elapsed = time.monotonic() - started
                if elapsed >= 360 and not marked:
                    marked = True
                    marker = {"observed_elapsed": elapsed, "over_budget": True,
                              "state": "running", "last_completed_scopes": last}
                    (output / "at-360-seconds.json").write_text(json.dumps(marker, indent=2) + "\n")
                    processes = subprocess.run(["ps", "-eo", "pid,ppid,etime,args"],
                                               text=True, capture_output=True, timeout=5)
                    (output / "processes-at-360.txt").write_text(processes.stdout)
                    print("DIAGNOSIS: 360s exceeded; continuing under separate 1800s safety cap.", flush=True)
                if finished.is_set():
                    break
                finished.wait(0.1)

    monitor = threading.Thread(target=observe, daemon=True)
    monitor.start()
    with (output / "test-output.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=1830)
        except subprocess.TimeoutExpired:
            # The original runner owns child-group cleanup at 1800s. This
            # outer guard is an infrastructure failure, not a completed run.
            process.kill()
            process.wait()
            code = 124
    elapsed = time.monotonic() - started
    finished.set()
    monitor.join(timeout=10)
    costs = json.loads(report.read_text()) if report.exists() else None
    modules = [] if costs is None else costs.get("modules", [])
    measurement = modules[0].get("measurement") if len(modules) == 1 else None
    completed = bool(measurement and measurement.get("tests_run") == 1
                     and measurement.get("successful") and code == 0)
    result = {"observed_seconds": elapsed, "exit": code,
              "full_lifecycle_completed": completed,
              "over_360_seconds": elapsed > 360,
              "natural_total_seconds": elapsed if completed else None,
              "after_360_seconds": max(0, elapsed - 360) if completed else None,
              "ci_acceptance": False,
              "state": "completed" if completed else "incomplete-or-failed"}
    (output / "diagnostic-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    print((output / "test-output.log").read_text(), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
