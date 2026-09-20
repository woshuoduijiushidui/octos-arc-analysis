# H01 Task-Evidence Injection Boundary

- Date: 2026-09-19
- Status: Accepted for M1-M4 implementation
- Baseline: `c599d18c5acd2b846f049ffea2be84e72fe60fac`
- Branch: `feat/h01-evidence-capsule`

## Context

H01 must preserve the current ARC requirement and runner-owned verification
evidence across context compaction. M0 first establishes which compaction path
the Python ARC stdio driver actually uses.

The observed production call chain is:

1. `arc/main.py::OctosDriver` defaults to `OCTOS_DRIVER=stdio` and calls
   `OctosDriver::_run_stdio`.
2. `arc/octos_stdio.py::OctosStdioSession::run_turn` sends `turn/start` with a
   text `InputItem`.
3. `ui_protocol_transport.rs::handle_turn_start_with_accept` resolves the
   session runtime and calls `appui_context_history_for_agent`.
4. That function loads the canonical `ContextManager`, performs threshold
   compaction when needed, and projects the model-visible history.
5. The turn-specific Agent is given an `AppUiPromptContextBridge` through
   `Agent::with_prompt_context_manager`.
6. `Agent::process_message_tracked_with_attachments` calls
   `prepare_prompt_with_context_manager` before each provider request.
7. The bridge performs in-loop semantic compaction. Its deterministic path is
   `PromptFrame::compact_summary` ->
   `compact_messages_with_prior_summaries` -> `compact_messages`.
8. `agent/llm_call.rs` sends the resulting prompt through
   `LlmProvider::chat`.

Attaching the bridge disables the Agent's legacy, declarative, and tiered
compaction mutations. H01 therefore has to integrate with `ContextManager` and
the AppUI bridge; changing only `Agent::trim_to_context_window` or a workspace
`CompactionRunner` would not affect ARC stdio turns.

The M0 characterization test
`arc_stdio_compaction_characterization_exposes_task_evidence_loss` forces this
bridge to compact a controlled ARC-like transcript. It records the current
behavior:

- only the first line of an older multi-line requirement reaches the summary;
- a tool result beginning with `Process exited with code 1` is labeled `ok`
  because it does not begin with `Error:`;
- the later expected/actual failure detail is absent;
- the newest user request remains raw.

This is test-observer proof of the target path and does not call a model.

## Baseline Policy

- Semantic boundary mode is on when
  `OCTOS_OUP_SEMANTIC_CONTEXT_MODE` is unset.
- Automatic compaction triggers above 70% of the provider context window,
  unless `OCTOS_CONTEXT_COMPACT_THRESHOLD_TOKENS` overrides it.
- The target is two thirds of the trigger threshold, unless
  `OCTOS_CONTEXT_COMPACT_TARGET_TOKENS` supplies a valid lower value.
- The deterministic summary budget is roughly one third of the target,
  clamped to 256-4096 tokens and below the target.
- ARC does not pass `--llm-compaction`; the default path adds no provider
  request.
- Tool output keeps at most 8 KiB model-visible. Truncated output, or output
  above the 16 KiB inline threshold, receives a logical
  `tool-output/sha256:<digest>.txt` reference persisted under the session data
  root's `context_ledgers/` directory.

## Session Scope

`OCTOS_SESSION_SCOPE=turn` is the ARC default. `OctosDriver::run` closes the
stdio process after every design, implement, and repair turn, so H01 mainly
protects evidence within one long tool-using turn. Each new turn must still
receive a complete capsule from the Python orchestrator.

With `OCTOS_SESSION_SCOPE=node`, design, implementation, and repair turns for
one requirement reuse the same stdio session. `Flow` calls
`driver.end_scope("node")` at node boundaries, which closes that session.
This mode makes deterministic replacement of the prior capsule especially
important because several outer turns share one canonical transcript.

## Decision

Use a typed UI-protocol input boundary:

1. Python owns and persists `.arc/context/task-evidence.v1.json`.
2. `arc/octos_stdio.py` sends the validated capsule beside the existing text
   item in `turn/start`.
3. Add a versioned `InputItem::TaskEvidence` payload. Older servers already
   deserialize unknown input kinds as `InputItem::Unknown`; because the text
   item remains present, they retain existing behavior.
4. The Rust transport validates size, schema, paths, and hashes, then records a
   dedicated typed `ContextManager` transcript item.
5. `ContextManager` keeps only the newest valid task-evidence item in the
   active projection. Both pre-turn and in-loop compaction consume that same
   canonical item.
6. Prompt projection renders it as bounded task and verification state, not as
   a user instruction. The newest real user message remains the current
   command.

The capsule gets a separate budget from the existing plan snapshot. Its
trusted verdict fields come only from ARC requirement parsing and acceptance
runner results.

## Rejected Alternatives

- **Markers inside ordinary prompt text:** rejected because a user can forge
  them, compaction can summarize them, and replacing an old capsule requires
  parsing untrusted prose.
- **Only a generic `ContextInjection`:** rejected because it lacks the H01
  schema/version contract, trusted field ownership, latest-only replacement
  semantics, and a distinct budget.
- **Only Agent legacy/declarative compaction:** rejected because ARC stdio
  attaches a caller-owned prompt context manager and those paths return
  without mutating the prompt.
- **Only Python prompt repetition:** rejected because it changes ordinary text
  prompts, does not survive in-loop compaction as typed state, and cannot
  distinguish runner evidence from model-authored text.
- **A second artifact store:** rejected because `ToolOutputEnvelope` already
  provides content-addressed raw output references and atomic persistence.

## Consequences

M1 builds the task-local Python reducer. M2 adds the wire type and canonical
transcript item. M3 changes deterministic selection and budgeting. M4 reuses
the existing tool-output artifact mechanism. M0 deliberately implements none
of those behavior changes.

## Verification

All results below were captured on the baseline and branch named above.

| Command | Result |
| --- | --- |
| `cargo test -p octos-cli arc_stdio_compaction_characterization_exposes_task_evidence_loss --lib -- --nocapture` | 1 passed |
| `cargo test -p octos-agent --lib compaction` | 64 passed |
| `cargo test -p octos-agent --test compaction_policy` | 12 passed |
| `cargo test -p octos-cli context_manager --lib` | 96 passed |
| `cargo test -p octos-cli compaction --lib` | 41 passed |

The literal repository-root command
`python3 -m unittest discover -s arc/tests` stopped with 14 import errors
because `arc/` was not on the module path. The valid equivalent,
`PYTHONPATH=arc python3 -m unittest discover -s arc/tests`, ran 179 tests:
173 passed, 5 skipped, and 1 errored. The error was
`RuntimeCacheProvenanceTests.test_should_replace_a_stale_archive_before_recording_its_new_source`;
Python 3.9.6 does not support the code's
`tarfile.TarFile.extract(..., filter="data")` call. No newer Python executable
was available. This baseline interpreter incompatibility is outside H01.

`cargo fmt --all -- --check` and `git diff --check` passed.

No model ID or credentials were configured. M0 used the deterministic test
observer and made no provider request.
