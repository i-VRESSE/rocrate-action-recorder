## cyclopts adapter tasks

- [x] Task 1 — Single-level subcommand recording
- [x] Task 2 — Nested subcommand recording
- [x] Task 7 - Handle StdioPath, when stdin or stdout then do not record
- [x] Task 3 — `list[Path]` / `tuple[Path, ...]` multi-value arguments
- [x] Task 4 — File-like objects with `.name`
- [x] Task 5 — Multi-value argument with mixed real paths and stdio
- [x] Task 6 — Optional and default path arguments
- [ ] Task 8 — Root-level `RECORD_TRIGGER` with subcommands (trigger flag on root app is invisible to subcommand argument collection; recording always/never happens incorrectly)
- [ ] Task 9 — Flattened sub-apps (`app.command(sub_app, name="*")`): wrong argument collection resolved when subcommand is flattened into parent
- [ ] Task 10 — `*args` variable positional IO paths: tuple stored in `bound_args` falls through `search()` with no tuple branch, silently missing all paths
- [x] Task 11 — String tokens with spaces in paths: `argv.split()` used instead of `shlex.split`, producing corrupted action IDs for paths containing spaces
- [x] Task 12 — Pydantic/attrs/NamedTuple nested IO paths: `is_dataclass()` misses these types, so paths nested inside Pydantic/attrs models are silently skipped
- [x] Task 13 — Async commands: verify recording timing and return value handling for `async def` commands
- [x] Task 14 — Meta App entry point (`app.meta()`): unsupported/untested pattern, may record at wrong moment or with wrong context
- [x] Task 15 - Add pydantic to test deps and run/fix tests that need pydantic installed
