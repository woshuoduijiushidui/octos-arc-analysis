# H01 M3 Implementation and Verification

Date: 2026-09-19

Branch: `feat/h01-evidence-capsule`

## Scope

M3 makes deterministic compaction evidence-first without adding a model call.
The task capsule remains a typed `ContextManager` item and is not copied into
the narrative summary.

Implementation files in `octos-arc`:

- `crates/octos-agent/src/compaction.rs`
- `crates/octos-cli/src/api/context_manager.rs`
- `crates/octos-cli/src/api/ui_protocol_transport.rs`
- `crates/octos-cli/src/api/ui_protocol_tests.rs`
- `crates/octos-core/src/ui_protocol_tests.rs`

## Implemented Invariants

- The model-visible capsule has its own 16 KiB limit.
- Capsule sections are emitted in this order: task contract, active failures,
  latest verification, verified behavior, source/change facts, next action.
- Plan preservation remains inside the summary budget. The final
  `ContextManager` candidate accounts for the bounded capsule, plan-bearing
  summary, and retained raw tail together.
- Typed capsule items are excluded from the compactor input. Stale or forged
  `<task_evidence>` blocks are stripped from deterministic and LLM summaries
  before the latest typed item is projected.
- Tool output envelopes record `execution_status` and `exit_code`. A non-zero
  process exit is failure even when its text does not start with `Error:`;
  legacy text without structured status is reported as unknown.
- LLM compaction receives only allowlisted tool argument fields. Arbitrary
  arguments and unsafe commands are omitted.
- Empty summaries and candidates that do not reduce the token estimate are
  rejected before changing the active generation.
- Failed or infeasible attempts preserve the current active history and use
  the existing input/candidate fingerprint suppression until compactable input
  changes.
- If pre-turn, in-loop, or manual-compaction snapshot persistence fails, the
  replacement is discarded; the in-loop model prompt is restored exactly.

## Deterministic Scenario Coverage

| Research scenario | Automated coverage |
| --- | --- |
| 1. Multi-line requirement survives | `task_evidence_and_plan_fit_separate_budgets_under_the_total_target` |
| 2. Latest failure fields survive a small summary budget | `task_evidence_and_plan_fit_separate_budgets_under_the_total_target` |
| 3. Non-zero exit code is failure | `structured_tool_exit_code_overrides_legacy_text_prefix_heuristic`; ARC bridge characterization |
| 4. Tool arguments are allowlisted | `llm_compaction_transcript_preserves_tool_structure_without_hidden_reasoning` |
| 5. Repeated failure deduplicates | Python `test_should_deduplicate_same_failure_across_distinct_runs` |
| 6. Pass becomes regression after source/result change | Python `test_should_replace_pass_with_regression_for_the_current_source` |
| 7. Repeated compaction does not duplicate summary/plan/capsule | `task_evidence_survives_legacy_and_repeated_semantic_compaction`; `compaction_strips_task_evidence_blocks_before_reinjection` |
| 8. Empty/error/oversize/persistence failures preserve prior state | `compaction_candidate_that_is_not_smaller_is_rejected_without_mutation`; `arc_stdio_compaction_persistence_failure_keeps_the_previous_prompt`; existing LLM fallback and over-budget tests |
| 9. Tool pairing and newest user/system invariants remain | existing ContextManager and agent compaction suites; `arc_stdio_typed_task_evidence_survives_pre_turn_and_in_loop_compaction` |

## Verification

Passed:

```text
cargo test -p octos-core ui_protocol::tests --lib
165 passed

cargo test -p octos-cli context_manager --lib
102 passed

cargo test -p octos-cli task_evidence --lib -- --nocapture
7 passed

cargo test -p octos-cli compaction --lib
45 passed

cargo test -p octos-agent --lib compaction
66 passed

cargo test -p octos-agent --test compaction_policy
12 passed
```

`cargo check -p octos-cli --lib`, `cargo fmt --all -- --check`, and
`git diff --check` passed.

Full Python discovery ran 195 tests with 5 skips. The only error remains the
pre-existing Python 3.9 incompatibility in
`RuntimeCacheProvenanceTests.test_should_replace_a_stale_archive_before_recording_its_new_source`:

```text
TypeError: extract() got an unexpected keyword argument 'filter'
```

`cargo clippy` remains unavailable in the installed Rust toolchain.

No commit or push was performed.
