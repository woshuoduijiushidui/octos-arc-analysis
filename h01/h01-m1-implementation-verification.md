# H01 M1 Implementation and Verification

Date: 2026-09-19

Branch: `feat/h01-evidence-capsule`

## Scope

M1 adds the ARC-side deterministic task evidence reducer. It does not add the
Rust typed transport or change compaction behavior; those remain M2 and M3.

Implementation files in `octos-arc`:

- `arc/task_evidence.py`
- `arc/acceptance.py`
- `arc/main.py`
- `arc/tests/test_task_evidence.py`
- `arc/tests/test_acceptance.py`
- `arc/tests/test_codegen.py`
- `arc/tests/test_main_helpers.py`

The current capsule is written to:

`<output_dir>/.arc/context/task-evidence.v1.json`

## Implemented Invariants

- Task contracts are derived from the loaded requirement tree, normalized
  scenarios, transitive dependencies, containment ancestors, and the read-only
  requirement source path.
- Requirement and source tree hashes use deterministic SHA-256 encodings.
- Verification verdicts come only from `RunSummary` and `TestOutcome`.
- Pass evidence is bound to both `run_id` and source tree hash and is
  invalidated after a source change.
- Active failures use stable signatures, deduplicate repeated observations,
  retain occurrence counts, and leave unreliable expected/actual values empty.
- Test commands are reconstructed only from allowlisted relative
  `*.spec.ts` paths.
- Capsule writes use a temporary file, flush/fsync, and atomic replace.
  Failed writes leave the previous capsule intact.
- Capsule updates cover existing-app probes, design/implement entry, tiny and
  regular node acceptance, regression cycles/checkpoints, every full-suite
  round, and best-state restoration.
- Invalid requirement sources and existing capsule schemas fail explicitly.
  Flow logs the failure and disables evidence rather than writing an empty
  capsule.

## Verification

Passed:

```text
PYTHONPATH=arc python3 -m unittest \
  arc.tests.test_task_evidence \
  arc.tests.test_acceptance \
  arc.tests.test_codegen

Ran 69 tests in 2.426s
OK (skipped=4)
```

```text
PYTHONPATH=arc python3 -m unittest \
  arc.tests.test_main_helpers.TaskEvidenceLifecycleTests \
  arc.tests.test_main_helpers.FinalSuiteBestRoundTests \
  arc.tests.test_main_helpers.AlreadyPassingProbeTests

Ran 7 tests in 0.055s
OK
```

```text
PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH" \
  cargo fmt --all -- --check

PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH" \
  cargo test -p octos-cli \
  arc_stdio_compaction_characterization_exposes_task_evidence_loss -- --nocapture

test result: ok. 1 passed; 0 failed
```

`git diff --check` and Python byte-compilation also passed.

Full Python discovery ran 191 tests with 5 skips. All M1 and related regression
tests passed. The only error is the pre-existing Python 3.9 incompatibility in
`RuntimeCacheProvenanceTests`:

```text
TypeError: extract() got an unexpected keyword argument 'filter'
```

The failure is in `tarfile.TarFile.extract(..., filter="data")`, a parameter
not supported by the workspace's Python 3.9.6 runtime. It is unrelated to M1
and was not changed in this milestone.

No commit or push was performed.
