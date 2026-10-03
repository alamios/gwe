# Agent instructions

## Scope and workflow

- Read `README.md` before working. For GPU changes, also read `docs/setup-compatibility.md`,
  `docs/maintenance-plan.md` and the relevant entries in `docs/technical-references.md`.
- Continue this maintenance phase on `maintenance/nvml-revival`. Preserve the inherited `release`
  baseline and any user changes. Do not reset to upstream using historical README commands.
- Keep repository documentation, code comments and commit descriptions in English.
- Keep user-specific environment paths and preferences in the user's global instructions, not project docs.
- Update affected documentation and keep README links and status accurate. Distinguish proposed behavior
  from implemented behavior and observed test results.

## GPU and system operations

- Start with read-only inspection and simulated backends. Launching GWE can reapply saved profiles and
  write GPU settings; it is not a read-only smoke test.
- Follow the user's current authorization for system inspection and hardware tests. Repository work alone
  does not authorize package/driver changes, access to personal profiles or fan/clock/power writes.
- Never run a development fan controller concurrently with another controller on the same GPU.
- Test missing/stale telemetry, permissions, partial writes, limits and automatic restoration when changing
  those behaviors. Ordinary cleanup cannot handle SIGKILL or a frozen process.
- Inspect build scripts before running them: they can regenerate the changelog and clear build output.
  Review the historical Flatpak submodule before building or installing development packages.

## Development environments

- Use Python 3.12 for the current-host baseline and Python 3.14 for target compatibility checks, as described
  in `docs/maintenance-plan.md`. Follow the user's global instructions for environment location and dependencies.
- Check dependencies and imports before starting the application. Do not install the historical requirements
  blindly or modify system Python to make them fit.
- Keep UI integration checks separate from backend tests. A Python 3.14 virtual environment on Ubuntu 24.04
  does not reproduce the Kubuntu 26.04 native library stack.
