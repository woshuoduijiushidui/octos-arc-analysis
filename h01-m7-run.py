#!/usr/bin/env python3
"""Run the frozen H01 A/B/C experiment and preserve per-test timestamps."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO = ROOT / "octos-arc"
STATE_ROOT = ROOT / ".h01-m7"
WORKTREE_ROOT = STATE_ROOT / "worktrees"
TARGET_DIR = STATE_ROOT / "target"
BIN_DIR = STATE_ROOT / "bin"
PLAYWRIGHT_ROOT = STATE_ROOT / "playwright"
PREPARED_PATH = STATE_ROOT / "prepared.json"
RESULT_ROOT = Path(__file__).resolve().parent / "h01-m7-results"

VARIANTS = {
    "A": "c599d18c5acd2b846f049ffea2be84e72fe60fac",
    "B": "6d7d1559b72c3b0a34789909d3056527fdc9d42d",
    "C": "804e42a8d42b5e570a5d1d2cb78b01d0a73059d7",
}

TASKS = {
    "small": {
        "id": "smoke--counter",
        "time_budget_s": 180,
        "node_time_budget_s": 180,
    },
    "medium": {
        "id": "ticket-booking--ticket-booking",
        "time_budget_s": 360,
        "node_time_budget_s": 210,
    },
    "long": {
        "id": "arc-bench-web--keep",
        "time_budget_s": 480,
        "node_time_budget_s": 180,
    },
}

FIXED_ENV = {
    "OCTOS_ARC_REASONING": "low",
    "OCTOS_ARC_MAX_TOKENS": "32768",
    "OCTOS_NODE_TIMEOUT": "150",
    "OCTOS_DESIGN_TIMEOUT": "60",
    "OCTOS_REPAIR_ROUNDS": "1",
    "OCTOS_FINAL_REPAIR_ROUNDS": "0",
    "OCTOS_MIN_REPAIR_SECONDS": "30",
    "OCTOS_DESIGN_TURN": "0",
    "OCTOS_DESIGN_MIN_NODES": "1",
    "OCTOS_DESIGN_MODE": "separate",
    "OCTOS_SKELETON_MIN_NODES": "999",
    "OCTOS_IMPLEMENT_FRACTION": "1.0",
    "OCTOS_ARC_TEST_WORKERS": "1",
    "OCTOS_ARC_FINAL_WORKERS": "4",
    "OCTOS_ARC_REGRESSION_CHECKPOINT": "0",
    "OCTOS_ARC_CODEGEN": "0",
    "OCTOS_CONTEXT_COMPACT_THRESHOLD_TOKENS": "1200",
    "OCTOS_CONTEXT_COMPACT_TARGET_TOKENS": "800",
    "OCTOS_OUP_SEMANTIC_CONTEXT_MODE": "on",
    "OCTOS_MAX_ITERATIONS": "8",
    "OCTOS_ARC_INSTALL_PLAYWRIGHT": "0",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return "sha256:" + digest.hexdigest()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def run_checked(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def git_output(worktree: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare_grader_dir(worktree: Path) -> None:
    grader = worktree / "arc" / "local-grader"
    if grader.is_symlink():
        if grader.resolve() != PLAYWRIGHT_ROOT.resolve():
            raise RuntimeError(f"unexpected grader symlink: {grader}")
        grader.unlink()
    grader.mkdir(exist_ok=True)
    modules = grader / "node_modules"
    if modules.is_symlink() or modules.exists():
        if modules.resolve() != (PLAYWRIGHT_ROOT / "node_modules").resolve():
            raise RuntimeError(f"unexpected grader node_modules: {modules}")
    else:
        modules.symlink_to(
            PLAYWRIGHT_ROOT / "node_modules",
            target_is_directory=True,
        )


def prepare() -> None:
    STATE_ROOT.mkdir(exist_ok=True)
    WORKTREE_ROOT.mkdir(exist_ok=True)
    BIN_DIR.mkdir(exist_ok=True)
    RESULT_ROOT.mkdir(exist_ok=True)

    for variant, sha in VARIANTS.items():
        worktree = WORKTREE_ROOT / variant
        if not worktree.exists():
            run_checked(
                ["git", "worktree", "add", "--detach", str(worktree), sha],
                SOURCE_REPO,
            )
        actual = git_output(worktree, "rev-parse", "HEAD")
        if actual != sha:
            raise RuntimeError(f"{variant} worktree is {actual}, expected {sha}")
        prepare_grader_dir(worktree)
        if git_output(worktree, "status", "--porcelain"):
            raise RuntimeError(f"{variant} worktree is dirty before build")

    if not (PLAYWRIGHT_ROOT / "node_modules" / "@playwright" / "test").is_dir():
        PLAYWRIGHT_ROOT.mkdir(exist_ok=True)
        if not (PLAYWRIGHT_ROOT / "package.json").is_file():
            run_checked(["npm", "init", "-y"], PLAYWRIGHT_ROOT)
        run_checked(
            ["npm", "install", "--no-audit", "--no-fund", "@playwright/test@1.63.0"],
            PLAYWRIGHT_ROOT,
        )
        run_checked(
            [str(PLAYWRIGHT_ROOT / "node_modules/.bin/playwright"), "install", "chromium"],
            PLAYWRIGHT_ROOT,
        )

    prepared_variants = {}
    for variant in VARIANTS:
        worktree = WORKTREE_ROOT / variant
        variant_target = TARGET_DIR / variant
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = str(variant_target)
        run_checked(
            [
                "cargo",
                "build",
                "--locked",
                "-p",
                "octos-cli",
                "--bin",
                "octos",
                "--no-default-features",
                "--features",
                "api",
            ],
            worktree,
            env,
        )
        binary = BIN_DIR / f"octos-{variant}"
        shutil.copy2(variant_target / "debug" / "octos", binary)
        binary.chmod(0o755)
        prepare_grader_dir(worktree)
        if git_output(worktree, "status", "--porcelain"):
            raise RuntimeError(f"{variant} worktree became dirty during prepare")
        prepared_variants[variant] = {
            "git_sha": VARIANTS[variant],
            "binary_sha256": sha256_file(binary),
        }
        print(
            f"prepared {variant} {VARIANTS[variant]} binary={sha256_file(binary)}",
            flush=True,
        )
    write_json(
        PREPARED_PATH,
        {
            "prepared_at": now(),
            "playwright_version": "1.63.0",
            "variants": prepared_variants,
        },
    )


def verify_prepared() -> None:
    if not PREPARED_PATH.is_file():
        raise RuntimeError("prepared manifest missing; run `h01-m7-run.py prepare`")
    prepared = json.loads(PREPARED_PATH.read_text(encoding="utf-8"))
    if not (PLAYWRIGHT_ROOT / "node_modules" / "@playwright" / "test").is_dir():
        raise RuntimeError("prepared Playwright installation is missing")
    for variant, sha in VARIANTS.items():
        worktree = WORKTREE_ROOT / variant
        binary = BIN_DIR / f"octos-{variant}"
        if not worktree.is_dir() or git_output(worktree, "rev-parse", "HEAD") != sha:
            raise RuntimeError(f"{variant} worktree does not match {sha}")
        if git_output(worktree, "status", "--porcelain"):
            raise RuntimeError(f"{variant} worktree is dirty")
        expected = prepared.get("variants", {}).get(variant, {})
        if expected.get("git_sha") != sha or not binary.is_file():
            raise RuntimeError(f"{variant} prepared artifact is missing or stale")
        actual_hash = sha256_file(binary)
        if expected.get("binary_sha256") != actual_hash:
            raise RuntimeError(
                f"{variant} binary changed after prepare: {actual_hash}"
            )


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def playwright_test_timings(report: dict) -> list[dict]:
    timings: list[dict] = []

    def walk(suites: list[dict], parent_file: str = "") -> None:
        for suite in suites or []:
            file_name = str(suite.get("file") or parent_file)
            for spec in suite.get("specs") or []:
                for test in spec.get("tests") or []:
                    results = test.get("results") or []
                    starts = [
                        parsed
                        for parsed in (
                            parse_timestamp(str(result.get("startTime") or ""))
                            for result in results
                        )
                        if parsed is not None
                    ]
                    ends = []
                    for result in results:
                        started = parse_timestamp(str(result.get("startTime") or ""))
                        if started is not None:
                            ends.append(
                                started
                                + timedelta(milliseconds=int(result.get("duration") or 0))
                            )
                    started_at = min(starts).isoformat(timespec="milliseconds") if starts else None
                    ended_at = max(ends).isoformat(timespec="milliseconds") if ends else None
                    timings.append(
                        {
                            "title": str(spec.get("title") or "?"),
                            "file": str(spec.get("file") or file_name),
                            "project": str(test.get("projectName") or ""),
                            "status": str((results[-1] if results else {}).get("status") or "unknown"),
                            "ok": bool(
                                test.get("status") == "expected" or test.get("ok")
                            ),
                            "started_at": started_at,
                            "ended_at": ended_at,
                            "duration_ms": sum(
                                int(result.get("duration") or 0) for result in results
                            ),
                        }
                    )
            walk(suite.get("suites") or [], file_name)

    walk(report.get("suites") or [])
    return timings


def jsonl(path: Path) -> list[dict]:
    records = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def usage_totals(path: Path) -> dict:
    totals = {
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "h01e_extra_requests": 0,
        "h01e_extra_tokens": 0,
    }
    for record in jsonl(path):
        totals["requests"] += int(record.get("requests") or 1)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "prompt_cache_hit_tokens",
        ):
            totals[key] += int(record.get(key) or 0)
        if record.get("request_kind") == "h01e_compaction":
            totals["h01e_extra_requests"] += 1
            totals["h01e_extra_tokens"] += int(record.get("prompt_tokens") or 0)
            totals["h01e_extra_tokens"] += int(record.get("completion_tokens") or 0)
    totals["provider_tokens"] = (
        totals["prompt_tokens"] + totals["completion_tokens"]
    )
    return totals


def compaction_records(path: Path) -> list[dict]:
    return [
        record
        for record in jsonl(path)
        if record.get("method") == "context/compaction_completed"
    ]


def installed_compaction_records(records: list[dict]) -> list[dict]:
    return [
        record
        for record in records
        if (record.get("params") or {}).get("compaction", {}).get("status")
        == "installed"
    ]


def artifact_index(arc_dir: Path) -> list[dict]:
    indexed = []
    for relative in (
        "llm-usage.jsonl",
        "runner-events.jsonl",
        "octos-events.jsonl",
        "local-grade.json",
        "final-grade-report.json",
        "test-times.jsonl",
        "compaction-events.jsonl",
        "context/task-evidence.v1.json",
    ):
        path = arc_dir / relative
        if path.is_file():
            indexed.append(
                {
                    "path": f".arc/{relative}",
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    evidence_dir = arc_dir / "evidence"
    if evidence_dir.is_dir():
        for path in sorted(p for p in evidence_dir.rglob("*") if p.is_file()):
            indexed.append(
                {
                    "path": f".arc/evidence/{path.relative_to(evidence_dir).as_posix()}",
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return indexed


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_one(
    variant: str,
    task_size: str,
    repetition: int,
    run_order: int,
    scope: str,
    phase: str,
    port: int,
) -> dict:
    config = TASKS[task_size]
    task_id = config["id"]
    worktree = WORKTREE_ROOT / variant
    task_dir = worktree / "arc" / "tasks" / task_id
    tests_dir = worktree / "arc" / "public-tests" / task_id
    binary = BIN_DIR / f"octos-{variant}"
    output_name = (
        f"h01-m7-{phase}-{task_size}-r{repetition}-{variant.lower()}-o{run_order}"
    )
    output = worktree / "arc" / "arc-output" / output_name
    if output.exists():
        raise RuntimeError(f"refusing to reuse output directory: {output}")
    if git_output(worktree, "status", "--porcelain"):
        raise RuntimeError(f"{variant} worktree is dirty before {output_name}")

    endpoint = urlparse(os.environ["OPENAI_BASE_URL"])
    time_budget = (
        180 if phase in {"preflight", "default-scope"} else config["time_budget_s"]
    )
    node_budget = min(config["node_time_budget_s"], time_budget)
    manifest = {
        "experiment": "h01-abc-v1",
        "phase": phase,
        "variant": variant,
        "branch": {
            "A": "main@baseline",
            "B": "feat/h01-evidence-capsule",
            "C": "exp/h01e-llm-checkpoint",
        }[variant],
        "git_sha": VARIANTS[variant],
        "git_dirty": False,
        "git_status_porcelain": "",
        "task_size": task_size,
        "task_id": task_id,
        "requirements_sha256": sha256_file(task_dir / "requirements.yaml"),
        "tests_sha256": sha256_tree(tests_dir),
        "template_kind": "empty",
        "template_sha256": sha256_bytes(b""),
        "dependency_lock_present": False,
        "dependency_lock_sha256": sha256_bytes(b""),
        "binary_sha256": sha256_file(binary),
        "model": os.environ["MODEL"],
        "endpoint_id": f"{endpoint.scheme}://{endpoint.netloc}",
        "reasoning": FIXED_ENV["OCTOS_ARC_REASONING"],
        "temperature": "runtime_default",
        "max_output_tokens": int(FIXED_ENV["OCTOS_ARC_MAX_TOKENS"]),
        "session_scope": scope,
        "generation_mode": {
            "codegen": FIXED_ENV["OCTOS_ARC_CODEGEN"] != "0",
            "design": FIXED_ENV["OCTOS_DESIGN_MODE"],
        },
        "compaction_policy": {
            "threshold_tokens": int(
                FIXED_ENV["OCTOS_CONTEXT_COMPACT_THRESHOLD_TOKENS"]
            ),
            "target_tokens": int(
                FIXED_ENV["OCTOS_CONTEXT_COMPACT_TARGET_TOKENS"]
            ),
            "semantic_mode": FIXED_ENV["OCTOS_OUP_SEMANTIC_CONTEXT_MODE"],
        },
        "time_budget_s": time_budget,
        "node_time_budget_s": node_budget,
        "node_timeout_s": int(FIXED_ENV["OCTOS_NODE_TIMEOUT"]),
        "design_timeout_s": int(FIXED_ENV["OCTOS_DESIGN_TIMEOUT"]),
        "repair_rounds": int(FIXED_ENV["OCTOS_REPAIR_ROUNDS"]),
        "playwright_workers": {
            "generation": int(FIXED_ENV["OCTOS_ARC_TEST_WORKERS"]),
            "final_grade": int(FIXED_ENV["OCTOS_ARC_FINAL_WORKERS"]),
        },
        "tool_permissions": "octos serve --stdio --solo --danger-full-access",
        "machine": platform.platform(),
        "repetition": repetition,
        "run_order": run_order,
        "run_started_at": now(),
        "generation_started_at": None,
        "generation_ended_at": None,
        "grading_started_at": None,
        "grading_ended_at": None,
        "run_ended_at": None,
    }
    write_json(output / ".arc" / "experiment-manifest.json", manifest)

    env = os.environ.copy()
    env.update(FIXED_ENV)
    env.update(
        {
            "OCTOS_BIN": str(binary),
            "OCTOS_H01_VARIANT": variant,
            "OCTOS_SESSION_SCOPE": scope,
            "OCTOS_TIME_BUDGET": str(time_budget),
            "OCTOS_NODE_TIME_BUDGET": str(node_budget),
            "OCTOS_ARC_PLAYWRIGHT_ROOT": str(PLAYWRIGHT_ROOT),
        }
    )
    if variant == "C":
        env["OCTOS_H01E_LLM_CHECKPOINT"] = "1"
    else:
        env.pop("OCTOS_H01E_LLM_CHECKPOINT", None)

    log_path = RESULT_ROOT / "logs" / f"{output_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["generation_started_at"] = now()
    write_json(output / ".arc" / "experiment-manifest.json", manifest)
    with log_path.open("w", encoding="utf-8") as log:
        generation = subprocess.run(
            [
                sys.executable,
                str(worktree / "arc" / "run-task-local.py"),
                str(task_dir),
                "--name",
                output_name,
                "--port",
                str(port),
                "--smoke-port",
                str(port + 1),
            ],
            cwd=worktree,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    manifest["generation_ended_at"] = now()
    manifest["generation_exit_code"] = generation.returncode

    grade_log = RESULT_ROOT / "logs" / f"{output_name}-grade.log"
    manifest["grading_started_at"] = now()
    with grade_log.open("w", encoding="utf-8") as log:
        grading = subprocess.run(
            [
                sys.executable,
                str(worktree / "arc" / "grade-local.py"),
                str(output),
                task_id,
                str(port),
            ],
            cwd=worktree,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    manifest["grading_ended_at"] = now()
    manifest["grading_exit_code"] = grading.returncode

    report_path = (
        worktree
        / "arc"
        / "local-grader"
        / "run"
        / f"{task_id}-{output_name}"
        / "report.json"
    )
    report = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        shutil.copy2(report_path, output / ".arc" / "final-grade-report.json")
    timings = playwright_test_timings(report)
    timing_path = output / ".arc" / "test-times.jsonl"
    timing_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in timings),
        encoding="utf-8",
    )

    events_path = output / ".arc" / "octos-events.jsonl"
    compaction_attempts = compaction_records(events_path)
    compactions = installed_compaction_records(compaction_attempts)
    compaction_path = output / ".arc" / "compaction-events.jsonl"
    compaction_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False) + "\n"
            for item in compaction_attempts
        ),
        encoding="utf-8",
    )
    usage = usage_totals(output / ".arc" / "llm-usage.jsonl")
    grade = {}
    grade_path = output / ".arc" / "local-grade.json"
    if grade_path.is_file():
        grade = json.loads(grade_path.read_text(encoding="utf-8"))

    invalid_reasons = []
    if generation.returncode != 0:
        invalid_reasons.append("generation_process_error")
    if grading.returncode != 0 or not grade:
        invalid_reasons.append("grading_infrastructure_error")
    if not compactions:
        invalid_reasons.append("no_installed_compaction")
    if variant == "C" and compactions and usage["h01e_extra_requests"] == 0:
        invalid_reasons.append("c_missing_h01e_request")
    if variant != "C" and usage["h01e_extra_requests"] != 0:
        invalid_reasons.append("unexpected_h01e_request")
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if "insufficient_balance" in log_text or "authentication failed" in log_text:
        invalid_reasons.append("provider_account_error")
    if "out of memory" in log_text.lower() or "likely out of memory" in log_text.lower():
        invalid_reasons.append("oom")

    manifest.update(
        {
            "run_ended_at": now(),
            "compaction_attempt_count": len(compaction_attempts),
            "compaction_count": len(compactions),
            "usage": usage,
            "grade": {
                "passed": int(grade.get("passed") or 0),
                "total": int(grade.get("total") or 0),
            },
            "test_timing_count": len(timings),
            "valid": not invalid_reasons,
            "invalid_reasons": invalid_reasons,
            "output_dir": str(output),
            "generation_log": str(log_path),
            "grading_log": str(grade_log),
        }
    )
    write_json(output / ".arc" / "artifact-index.json", artifact_index(output / ".arc"))
    write_json(output / ".arc" / "experiment-manifest.json", manifest)
    write_json(
        RESULT_ROOT / f"{output_name}.json",
        {"manifest": manifest, "test_timings": timings},
    )
    print(
        f"[{now()}] completed {output_name}: "
        f"grade={manifest['grade']['passed']}/{manifest['grade']['total']} "
        f"compactions={len(compactions)} tokens={usage['provider_tokens']} "
        f"valid={manifest['valid']}",
        flush=True,
    )
    return manifest


def run_suite(port: int) -> None:
    order = 0
    preflight = []
    for variant in ("A", "B", "C"):
        order += 1
        preflight.append(
            run_one(variant, "long", 0, order, "node", "preflight", port)
        )
    if any(item["compaction_count"] == 0 for item in preflight):
        raise RuntimeError(
            "preflight did not trigger compaction for every variant; "
            "inspect h01-m7-results before changing the frozen threshold"
        )

    rotations = (("A", "B", "C"), ("B", "C", "A"), ("C", "A", "B"))
    for task_size in ("small", "medium", "long"):
        for repetition, variants in enumerate(rotations, 1):
            for variant in variants:
                order += 1
                run_one(
                    variant,
                    task_size,
                    repetition,
                    order,
                    "node",
                    "main",
                    port,
                )

    for variant in ("A", "B", "C"):
        order += 1
        run_one(
            variant,
            "long",
            1,
            order,
            "turn",
            "default-scope",
            port,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run-all", "run-one"))
    parser.add_argument("--variant", choices=tuple(VARIANTS))
    parser.add_argument("--task-size", choices=tuple(TASKS))
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--run-order", type=int, default=1)
    parser.add_argument("--scope", choices=("turn", "node", "run"), default="node")
    parser.add_argument("--phase", default="manual")
    parser.add_argument("--port", type=int, default=43100)
    args = parser.parse_args()

    if args.command == "prepare":
        prepare()
        return 0
    for required in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL"):
        if not os.environ.get(required):
            raise RuntimeError(
                f"{required} is missing; run `source ~/.zshrc` before the experiment"
            )
    verify_prepared()
    if args.command == "run-all":
        run_suite(args.port)
    else:
        if not args.variant or not args.task_size:
            parser.error("run-one requires --variant and --task-size")
        run_one(
            args.variant,
            args.task_size,
            args.repetition,
            args.run_order,
            args.scope,
            args.phase,
            args.port,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
