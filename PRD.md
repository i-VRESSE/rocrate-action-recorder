# PRD: Cyclopts Adapter — Advanced Functionality

**Status:** Draft  
**Date:** 2026-03-27  



## Tasks

- [x] Task 1 — Single-level subcommand recording
- [ ] Task 2 — Nested subcommand recording
- [ ] Task 3 — `list[Path]` / `tuple[Path, ...]` multi-value arguments
- [ ] Task 4 — File-like objects with `.name`
- [ ] Task 5 — Multi-value argument with mixed real paths and stdio
- [ ] Task 6 — Optional and default path arguments



## Problem Statement

The `rocrate-action-recorder` Cyclopts adapter (`rocrate_action_recorder.adapters.cyclopts`) currently supports single-command CLIs with individual `Path` arguments. Users who build real-world Cyclopts CLIs with subcommands, multi-value path arguments, file-like objects, optional paths, or stdin/stdout placeholders cannot reliably record their program invocations because:

1. **Subcommands** are extracted as a flat dictionary of all possible subapps but the *executed* subcommand is never resolved, so the recorded metadata points to the wrong command.
2. **`list[Path]` / `tuple[Path, ...]`** is nominally delegated to `value2paths()` but is never tested for Cyclopts-specific binding, leaving coercion correctness unverified.
3. **File-like objects** with a `.name` attribute (custom converters, wrapper types) are not exercised, so users cannot confirm that the shared `try_convert_to_path()` filtering actually works in the Cyclopts call flow.
4. **Optional and default path arguments** (e.g. `output: Path | None = None`) cause spurious warnings or silent data loss.
5. **Stdin/stdout placeholders** (`-`, `<stdin>`, `<stdout>`) from custom Cyclopts converter types are not tested, so warning-and-skip semantics are unconfirmed.



## Solution

Extend the Cyclopts adapter to:
- Resolve the *executed* subcommand path at runtime and record it accurately into the `Program` hierarchy.
- Verify and harden multi-value path argument coercion for all Cyclopts-native container types.
- Confirm correct handling of file-like converter objects and StdioPath-style wrappers.
- Silently skip `None`/missing optional path arguments without spurious warnings.
- Achieve full test parity with the argparse and click adapters for all features targeted in this PRD.

## User Stories

### Subcommands

1. As a CLI author, I want a single-level subcommand invocation to be recorded with the name of the command that was actually called, so that provenance metadata is unambiguous.
2. As a CLI author, I want a two-level nested subcommand (e.g. `tool remote add`) to be recorded with the full command hierarchy in the `Program.subcommands` tree, so that the RO-Crate reflects the precise call path.
3. As a CLI author, I want input/output arguments belonging to a subcommand to be resolved from that subcommand's parameter set, not from the root app, so that sibling subcommands with overlapping parameter names do not interfere.
4. As a CLI author, I want a `RECORD_TRIGGER` annotation on a subcommand parameter to gate recording correctly, so that the trigger only fires when its own subcommand is invoked.

### Multi-Value Path Arguments

5. As a CLI author, I want `list[Path]` parameters annotated with `INPUT_FILES` to produce one `IOArgumentPath` entry per path, so that all inputs appear in the RO-Crate.
6. As a CLI author, I want `tuple[Path, ...]` parameters to be coerced the same way as `list[Path]`, so that I can use Cyclopts' native variadic tuple typing without loss of recorded paths.
7. As a CLI author, I want duplicate paths in a multi-value argument to be deduplicated before recording, so that the RO-Crate does not contain redundant dataset entries.
8. As a CLI author, I want an empty `list[Path]` or zero-length `tuple[Path, ...]` to produce no `IOArgumentPath` entries and no spurious warning, so that optional variadic arguments do not pollute provenance.
9. As a CLI author, I want a single-element tuple input to be recorded as a single path, consistent with how a single-element list is handled.

### File-like Objects and StdioPath Wrappers

10. As a CLI author using a custom Cyclopts converter that returns a file-like object, I want the `.name` attribute to be resolved to a `Path` and recorded, so that converter-based arguments are fully supported.
11. As a CLI author, I want file-like objects whose `.name` is `-`, `<stdin>`, or `<stdout>` to be silently skipped with a `WARNING`-level log message, so that stdin/stdout usage does not pollute the RO-Crate with invalid dataset paths.
12. As a CLI author using a `StdioPath`-style wrapper type (a custom converter that transparently returns either a real `Path` or a stdio-placeholder file-like), I want the real path variant to be recorded and the stdio variant to be skipped, so that optional fallback-to-stdin arguments are handled gracefully.
13. As a CLI author, I want a multi-value argument that mixes real paths and stdin placeholders to record only the real paths, so that partial stdio usage does not suppress legitimate provenance data.

### Optional and Default Path Arguments

14. As a CLI author, I want an `Optional[Path]` argument that is not provided on the CLI to be silently skipped without a warning, so that sparse argument usage does not result in noisy logs.
15. As a CLI author, I want an `Optional[Path]` argument that *is* provided on the CLI to be recorded normally, so that optional paths are fully captured when present.
16. As a CLI author, I want a `Path` argument with a non-None default value that is overridden on the CLI to be recorded with the supplied value, so that explicit user intent is always captured.
17. As a CLI author, I want a `Path` argument that relies on its default value (i.e. not explicitly passed on the CLI) to still be recorded, consistent with argparse and click behaviour, so that default-driven workflows produce complete provenance.


## Implementation Decisions

### Subcommand Path Resolution

- `program_from_app()` currently builds a flat `subcommands` dict from all `app.subapps`. This remains useful as a full tree snapshot (consistent with how `recorded_argparse` attaches the full parser tree to `Program`).
- A new helper `_resolve_executed_subapp(app, argv)` will walk the parsed token list (identical to what `run_with_record` already normalises from `sys.argv`) and return the leaf `App` instance that was actually invoked.
- `collect_record_info_from_cyclopts()` will receive the resolved leaf `App` and its corresponding `ArgumentCollection` (assembled from the leaf, not the root), so that IO argument scanning is always scoped to the executing command.
- The `record_cyclopts()` signature will accept an additional `executed_app: App | None = None` parameter; if provided it overrides the root `app` for purpose of `program_from_app()` construction (root is still used for name).
- Approach mirrors Click's context-chain traversal (`program_from_context`) and argparse's `_subparsers` traversal (`program_from_parser`) but uses Cyclopts' own `App.parse_args()` return value (which already includes the bound leaf app) to avoid re-implementing token walking.

### Multi-Value Path Argument Coercion

- No changes to `shared.value2paths()` are required; it already iterates `list` and `tuple`.
- The gap is in test coverage only. New tests will exercise `tuple[Path, ...]`, `tuple[Path, Path]` (fixed-length), empty `list[Path]`, and single-element `tuple[Path]` through the full `collect_record_info_from_cyclopts()` path.
- Cyclopts delivers `tuple` for variadic positional parameters and `list` for parameters declared as `list[Path]`. Both are already handled by `value2paths()`.

### File-like Object and StdioPath Handling

- `shared.try_convert_to_path()` already filters `.name` values of `-`, `<stdin>`, `<stdout>`. No production code changes are needed.
- A minimal `_StdioPath` test helper (local to the test file, not a public type) will simulate a file-like wrapper whose `.name` is a real path or a stdio sentinel, validating the Cyclopts `collect_record_info_from_cyclopts()` path end-to-end.
- If a future public `StdioPath` converter utility is wanted, it should be defined in `shared.py` and will be a separate PRD.

### Optional and Default Path Arguments

- `value2paths()` (`shared.py`) calls `try_convert_to_path()` on each item; `try_convert_to_path()` returns `None` for falsy/None values and logs a debug message. `value2paths()` filters out `None` returns.
- The current `resolve()` closure in `collect_record_info_from_cyclopts()` emits a `WARNING` when `paths` is empty. This warning is appropriate when the marker asserts a path *must* exist but is inappropriate for genuinely optional arguments.
- A distinction will be made: `INPUT_FILE` / `OUTPUT_FILE` (singular marker) will retain the warning on empty result; `INPUT_FILES` / `OUTPUT_FILES` (plural marker) and arguments that resolve to `None` will be silently skipped.
- Alternatively (simpler): suppress the warning if the resolved bound-args value is `None` or an empty container, regardless of marker. This is the preferred approach — warn only when the value is non-None/non-empty but produces no valid paths (i.e. the value was present but unconvertable).

### Decorator API — `recorded_cyclopts`

- `recorded_cyclopts` is a function decorator factory with signature:
  ```python
  def recorded_cyclopts(
      app: App,
      *,
      crate_dir: Path | None = None,
      dataset_license: str | None = None,
  ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
  ```
- It wraps the decorated command function, captures `start_time` before original execution and `end_time` after, then calls `record_cyclopts()`.
- IO argument detection uses `app.assemble_argument_collection()` once at decoration time (same as `run_with_record`).
- The decorator does **not** need to monkey-patch `App.__call__`; it wraps the function directly, so lifecycle complexity is reduced relative to `run_with_record`.
- `recorded_cyclopts` and `run_with_record` share the same `_detect_ios_and_trigger`, `_should_record`, and `record_cyclopts` internals.



## Testing Decisions

### What makes a good test

Tests in this codebase exercise observable behaviour through public interfaces only. A good test reads like a specification: "given this CLI invocation, the RO-Crate records these inputs and outputs." Internals (function call order, monkey-patching mechanics, closure references) are tested only when they represent a meaningful user-visible contract (e.g. the argument-collection-reuse test that currently exists).

### Modules under test

All new tests belong in `tests/adapters/test_cyclopts.py`, extending the existing `TestRunWithRecord` class and adding new test classes as needed.

### Prior art

| New behaviour | Prior art to follow |
|||
| Subcommand recording | `Test_collect_record_info_from_argparse::test_subcommand_single_level`, `test_subcommand_nested_levels` |
| `tuple[Path, ...]` / `list[Path]` | `Test_collect_record_info_from_click::test_multiple_multiple`, `test_multiple_with_duplicates`, `test_nargs_int` |
| Empty multi-value / no-warning | `Test_collect_record_info_from_click::test_multiple_empty` |
| File-like `.name` resolve | `Test_collect_record_info_from_argparse::test_filetype_args` |
| Stdio skip + warning | `Test_collect_record_info_from_argparse::test_filetype_stdin`, `test_filetype_stdout` |
| Multi-value with mixed stdio | `Test_collect_record_info_from_click::test_filetype_multiple_with_stdin` |
| Optional absent path | `Test_collect_record_info_from_argparse::test_absent_optional_path` |
| Default path used | `Test_collect_record_info_from_argparse::test_arg_with_default` |
| Decorator basics | `Test_recorded_argparse::test_defaults`, `Test_recorded_click::test_defaults` |



## Task Checklists

### Task 1 — Single-level subcommand recording

**Goal:** `run_with_record` records the name and parameters of the invoked subcommand, not the root app.

- Write `test_subcommand_single_level` in `TestRunWithRecord`: invoke a two-subcommand app (`process`, `validate`), call `process`, assert recorded `Program.subcommands` reflects the `process` path.
- Implement `_resolve_executed_subapp(app, argv) -> App` to walk `App.parse_args()` result and return the leaf `App`.
- Update `run_with_record::patched_call` to assemble `argument_collection` from the resolved leaf app (not always the root).
- Update `collect_record_info_from_cyclopts` to accept an optional `executed_app` parameter used for `program_from_app()` program-name construction.
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.
- Run `uv run pyright` — no new type errors.

### Task 2 — Nested subcommand recording

**Goal:** A two-level nested command (e.g. `tool remote add`) records the full `Program` hierarchy.

- Write `test_subcommand_nested_levels` mirroring argparse/click equivalents: construct a three-level app, invoke the deepest command, inspect the `Program.subcommands` nesting.
- Extend `_resolve_executed_subapp` to recurse through multi-level subapp chains.
- Confirm `program_from_app()` builds the full tree from the root so the snapshot is complete.
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.
- Run `uv run pyright` — no new type errors.

### Task 3 — `tuple[Path, ...]` and `list[Path]` multi-value arguments

**Goal:** `collect_record_info_from_cyclopts` correctly records all paths from variadic parameters.

- Write `test_list_path_input_multiple` in a new `Test_collect_record_info_from_cyclopts` class: `list[Path]` parameter annotated `INPUT_FILES`, supply two distinct paths, assert two `IOArgumentPath` entries.
- Write `test_tuple_path_input_multiple`: `tuple[Path, ...]` parameter, two paths → two entries.
- Write `test_tuple_path_fixed_length`: `tuple[Path, Path]` with `nargs=2` → two entries.
- Write `test_list_path_duplicates`: supply same path twice → one deduplicated entry.
- Write `test_list_path_empty`: supply empty list → zero entries, no warning logged.
- Write `test_tuple_path_single_element`: single-element tuple → one entry.
- Ensure all tests pass without changing `value2paths()` (should be coverage, not code).
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.

### Task 4 — File-like objects with `.name`

**Goal:** Custom Cyclopts converter objects that expose a `.name` attribute are resolved to `Path`.

- Write `test_filetype_args`: define a minimal file-like class with a `.name` pointing to a real `tmp_path` file, pass it as bound value, assert path recorded.
- Write `test_filetype_stdin_ignored`: file-like with `.name = "<stdin>"` → zero paths, `WARNING` logged containing `"stdin"`.
- Write `test_filetype_stdout_ignored`: file-like with `.name = "<stdout>"` → zero paths, `WARNING` logged.
- Write `test_filetype_dash_ignored`: file-like with `.name = "-"` → zero paths, `WARNING` logged.
- Confirm no production code changes needed (relies on existing `shared.try_convert_to_path`).
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.

### Task 5 — Multi-value argument with mixed real paths and stdio

**Goal:** A list containing both real paths and stdio placeholders records only the real paths.

- Write `test_filetype_multiple_with_stdin`: `list` of two file-like objects — one real file, one `<stdin>` — assert one path recorded and one `WARNING` logged.
- Confirm behaviour consistent with `Test_collect_record_info_from_click::test_filetype_multiple_with_stdin`.
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.

### Task 6 — Optional and default path arguments

**Goal:** `None` and missing optional paths are silently skipped; present optional paths and CLI-overridden defaults are recorded.

- Write `test_absent_optional_path`: `input: Path | None = None`, do not pass on CLI, assert zero `IOArgumentPath` entries and **no warning logged**.
- Write `test_present_optional_path`: same signature, pass a real path on CLI, assert one entry recorded.
- Write `test_arg_with_default_overridden`: `Path` argument with non-None default, override on CLI, assert CLI value recorded.
- Write `test_arg_with_default_used`: same argument, do not override, assert default value recorded (consistent with argparse/click).
- Update `resolve()` closure in `collect_record_info_from_cyclopts` to suppress the "no path-like argument value" `WARNING` when the bound value is `None` or an empty container.
- Run `uv run pytest tests/adapters/test_cyclopts.py` — all tests green.
- Run `uv run pyright` — no new type errors.

## Out of Scope

- Redesign or modification of argparse or click adapters.
- A public `StdioPath` converter type in `shared.py` (mentioned as a future PRD item).
- Support for Cyclopts `Meta` commands (help/version subcommands generated by Cyclopts itself).
- Custom parameter converter registration or validation layering beyond what Cyclopts natively provides.
- Integration tests against real filesystem CLIs beyond what is needed to assert RO-Crate correctness.
- Non-path argument recording (integer, string, bool beyond `RECORD_TRIGGER`).

## Further Notes

- The `_ORIGINAL_CYCLOPTS_APP_CALL` module-level save and the `finally`-block restoration in `run_with_record` must be preserved across all changes. See repo memory note about stacked-patch risk from repeated calls.
- Cyclopts delivers `tuple` for variadic positional args and `list` for `list[T]` annotated params. Tests should cover both shapes explicitly to lock in this contract.
- The warning suppression for optional/None paths (Task 6) is the only production-code behavioural change outside of the new subcommand resolution and decorator. All other tasks are primarily test coverage work.
- `recorded_cyclopts` does **not** need monkey-patching because it wraps the command function directly before `App` dispatch; this is a simpler lifecycle than `run_with_record` and should be the recommended API going forward.
- The Cyclopts `parse_args()` return value is `(command, bound_args, unused_tokens)`. The first element (`command`) is the resolved leaf command function, not the leaf `App`. To resolve the leaf `App`, the implementation must walk `App.subapps` by matching the first non-flag token(s), or rely on `App.parse_intermixed_args()` if available. The exact mechanism should be confirmed against the installed Cyclopts version before implementation.
