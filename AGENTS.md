# Agent instructions

## Scope and workflow

- Read `README.md` before working. For GPU changes, also read `docs/architecture.md`,
  `docs/validation.md` and relevant entries in `docs/technical-references.md`.
- Develop on `main`. Preserve user changes, existing history/tags and the inherited baseline identified
  by `upstream-baseline`. Do not reset or rewrite history as part of maintenance.
- Keep documentation, code comments and commit descriptions in English.
- Keep user-specific environment paths and preferences in the user's global instructions, not project docs.
- Update affected documentation and README links. Distinguish implemented behavior, proposed behavior,
  simulated tests and observed hardware results.

## GPU and system operations

- Begin with read-only inspection and simulated backends. Normal GWE startup can reapply saved fan and
  power targets; it is not a read-only smoke test.
- Follow current user authorization for system inspection and hardware tests. Repository work alone
  does not authorize packages/drivers, personal profiles or fan/clock/power writes.
- Never run a development controller concurrently with another fan controller on the same GPU.
- Test missing/stale telemetry, permissions, partial writes, limits and verified restoration when changing
  those behaviors. Ordinary process cleanup cannot handle SIGKILL or a frozen process.
- Inspect build scripts before running them. Use `scripts/build_debs.py` for maintained native packages;
  it requires reviewed inputs and a new output directory. Do not invoke unrelated build/install paths.
- Do not push or publish without explicit user authorization. Prepare concrete reviewable artifacts first.

## Development environment

- Use system Python 3.14 on the target host for tests, GTK checks and native builds, with the reviewed
  standalone inputs described in `docs/packaging.md`. Follow global environment/dependency instructions.
- Check imports and prerequisites before launch. Do not install requirements blindly or modify system
  Python to satisfy dependencies; ask for setup assistance when needed.
- Keep backend, isolated GUI and installed hardware acceptance separate. Interpreter compatibility alone
  does not reproduce a target desktop's native library stack.
