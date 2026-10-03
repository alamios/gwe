# Contributing

Maintenance has resumed as an independent continuation of GreenWithEnvy. The initial target is a personal
RTX 3090 Ti setup on Kubuntu, with custom fan curves as the required feature. The validated support scope
remains limited. The chosen repository is [alamios/gwe](https://github.com/alamios/gwe),
maintained by alamios for the upcoming 1.0.0 release. This fork is maintained with AI assistance in
implementation, testing and documentation. Attribute the original work to
[Roberto Leinardi and the upstream contributors](https://gitlab.com/leinardi/gwe); that repository is not
the destination for this fork's changes or bug reports. Source and `.deb` releases are planned on GitHub;
Flatpak distribution is outside the current release scope.

## Working branch and scope

Development currently takes place on `maintenance/nvml-revival`; `release` preserves the upstream baseline.
Repository-specific instructions for coding agents are in [AGENTS.md](AGENTS.md).

Read the [assessment](docs/setup-compatibility.md), [plan](docs/maintenance-plan.md) and
[technical references](docs/technical-references.md) before changing GPU control.
Write maintained documentation, code comments and commit descriptions in English.
Preserve copyright notices and the GPL-3.0-or-later license.

## Development workflow

1. Record the behavior being changed and the affected hardware capability.
2. Begin with read-only queries and simulated backends. Do not launch the existing application against
   the live GPU as a harmless smoke test: startup may restore saved profiles and apply GPU settings.
3. Add meaningful tests for missing telemetry, permission failures, partial fan writes, bounds and recovery
   when implementing those behaviors. Run relevant tests and record what they establish.
4. Validate hardware writes using an agreed test procedure and a recovery plan. Keep development controllers
   separate from any controller already managing the GPU.
5. Update the assessment and plan as evidence changes. Separate observed results from proposed behavior.

The current build scripts may regenerate the changelog and clear build output. Inspect them before use.
The Flatpak submodule must be reviewed and initialized deliberately before a Flatpak build; it still points
at the historical upstream package. Follow [RELEASING.md](RELEASING.md) for distribution decisions.

## Standalone backend diagnostics

Use `python -m pytest -q` for simulated diagnostic tests; they do not access hardware.
Use `python -m gwe.nvml_probe` for an explicit read-only hardware snapshot. Neither command starts the GUI.
See [NVML diagnostics](docs/nvml-diagnostics.md) for environment requirements, exit codes and validated versions.

Repository-boundary tests for monitor-only integration also require `requirements-monitor-tests.txt`.
They verify that fan/clock/power writes cannot reach the driver in this mode. See [monitor mode](docs/monitor-mode.md)
for isolated configuration, the opt-in environment variable and the remaining GTK validation work.

For graphical development on the current host, use the [isolated source launcher](docs/gui-development.md)
in the Python 3.12 UI environment. Its `--smoke-test` performs a live read-only GPU/UI check; it is separate
from the simulated pytest suite and needs a graphical session.
