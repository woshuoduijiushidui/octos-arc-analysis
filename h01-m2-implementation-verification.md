# H01 M2 Implementation and Verification

Date: 2026-09-19

Branch: `feat/h01-evidence-capsule`

## Scope

M2 transports the M1 capsule through `turn/start` as typed data and preserves
one current capsule in the canonical `ContextManager` projection. It does not
change the M3 evidence-priority summary algorithm.

Implementation files in `octos-arc`:

- `arc/octos_stdio.py`
- `arc/tests/test_octos_stdio.py`
- `crates/octos-core/src/ui_protocol.rs`
- `crates/octos-core/src/ui_protocol_tests.rs`
- `crates/octos-cli/src/api/context_manager.rs`
- `crates/octos-cli/src/api/ui_protocol_transport.rs`
- `crates/octos-cli/src/api/ui_protocol_tests.rs`

## Implemented Contract

- `InputItem::TaskEvidence` carries the Python v1 capsule beside the unchanged
  text input.
- Rust validates the schema, 128 KiB limit, required fields, SHA-256 format,
  reference paths, allowlisted Playwright command, run/source consistency, and
  artifact metadata completeness before accepting the turn.
- `ContextManager` records evidence as `TranscriptItemKind::TaskEvidence` with
  supervisor ownership, not as a user or system transcript item.
- Revisions remain append-only in the canonical ledger, while the active
  projection keeps only the latest valid capsule.
- Snapshot restore validates evidence and reconstructs a latest-only active
  projection.
- Prompt projection labels the capsule as trusted task and verification data,
  not a user-authored instruction, and states that the newest real user
  message controls the current action.
- Both item-count and semantic compaction pin the same typed item. The ARC
  bridge test forces pre-turn and in-loop compaction and observes exactly one
  current capsule afterward.
- Text-only legacy payloads remain unchanged. Unknown input kinds retain the
  existing `InputItem::Unknown` fallback, so older servers can ignore the new
  item while still processing the text item.

## Verification

Passed:

```text
PYTHONPATH=arc python3 -m unittest \
  arc.tests.test_octos_stdio \
  arc.tests.test_task_evidence \
  arc.tests.test_main_helpers.TaskEvidenceLifecycleTests

Ran 15 tests
OK
```

```text
cargo test -p octos-core ui_protocol::tests --lib
165 passed

cargo test -p octos-cli context_manager --lib
98 passed

cargo test -p octos-cli compaction --lib
43 passed

cargo test -p octos-agent --lib compaction
64 passed

cargo test -p octos-agent --test compaction_policy
12 passed
```

The dedicated M2 filter passed 5 tests, including the real ARC prompt bridge:

```text
cargo test -p octos-cli task_evidence --lib -- --nocapture
5 passed
```

`cargo fmt --all -- --check`, `git diff --check`, Python byte-compilation, and
`cargo check -p octos-cli --lib` passed.

Full Python discovery ran 195 tests with 5 skips. The only error remains the
pre-existing Python 3.9 incompatibility in
`RuntimeCacheProvenanceTests.test_should_replace_a_stale_archive_before_recording_its_new_source`:

```text
TypeError: extract() got an unexpected keyword argument 'filter'
```

`cargo clippy` could not run because the installed Rust toolchain has no
Clippy component.

No commit or push was performed.
