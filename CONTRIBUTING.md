# Contributing

GreenWithEnvy is maintained by alamios at [alamios/gwe](https://github.com/alamios/gwe), with AI
assistance in implementation, testing and documentation. Report this fork's issues and submit changes
there. Preserve the original authors' credits, copyright notices and GPL-3.0-or-later license.

Develop on `main`. Read the [architecture](docs/architecture.md), [development guide](docs/development.md)
and [validation scope](docs/validation.md) before changing GPU behavior. Agent-specific instructions
are in [AGENTS.md](AGENTS.md). Use English for maintained documentation, comments and commits.

1. Describe the problem and expected behavior. Preserve existing user changes.
2. Begin with read-only inspection and simulated backends. Normal startup can apply saved GPU settings.
3. Test relevant missing/stale telemetry, permissions, bounds, partial writes and recovery failures.
4. Separate GUI/backend checks from explicitly authorized hardware acceptance. Never run competing fan
   controllers; prepare fresh baseline and recovery before writes.
5. Update affected documentation and validation. Distinguish implementation, simulated results and
   independent hardware observations.

Use [native packaging](docs/packaging.md) and the [release procedure](RELEASING.md). Do not change
drivers, kernels, system Python or CUDA as an incidental fix. Never include private databases, UUIDs,
profiles or raw logs in issues, commits or assets. Follow the [Code of Conduct](CODE_OF_CONDUCT.md).
