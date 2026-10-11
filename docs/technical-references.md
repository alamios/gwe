# Technical references

Primary references for implementation and review. Match the API and native libraries to the target
being tested; documentation alone does not prove permissions, hardware support or recovery behavior.

| Reference | Use |
| --- | --- |
| [NVML API reference](https://docs.nvidia.com/deploy/nvml-api/nvml-api-reference.html) | Library contracts and concurrency |
| [NVML device queries](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceQueries.html) | Telemetry, identity, power constraints, video engines and thresholds |
| [NVML device commands](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html) | Fan setters, automatic policies and power-limit commands |
| [NVML initialization and cleanup](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlInitializationAndCleanup.html) | Session lifecycle and sampling |
| [NVML change log](https://docs.nvidia.com/deploy/nvml-api/change-log.html) | Capability and binding changes |
| [NVIDIA Python bindings](https://pypi.org/project/nvidia-ml-py/) | Reviewed `pynvml` package |
| [GTK3 Wayland integration](https://docs.gtk.org/gtk3/wayland.html) | Native display backend |
| [GLib program identity](https://docs.gtk.org/glib/func.set_prgname.html) | Application identity and desktop integration |
| [PyGObject setup](https://pygobject.gnome.org/getting_started.html) | Python/native GTK setup; select GTK3 prerequisites |
| [SQLite backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup) | Consistent private database snapshots |
| [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) | Source tags and binary assets |

Application-specific guarantees and limits are documented in [architecture](architecture.md) and
[validation](validation.md). Keep driver/toolkit administration separate from application maintenance.
