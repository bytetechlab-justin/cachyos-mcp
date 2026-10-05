# MCP tool catalog

Generated from the installed server’s official MCP tools/list response. All user changes require a strict JSON `confirmed: true` after approval. Privileged tools also require administrator policy and authenticated sudo.

| Tool | Level | Description |
| --- | --- | --- |
| `create_desktop_entry` | 2 | Create a new KDE application launcher after approving its executable and arguments. |
| `create_directory` | 2 | Create a new private directory inside writable roots. |
| `create_file` | 2 | Create a new file inside writable roots after user approval; never overwrite. |
| `create_plasma_widget_project` | 2 | Create a Plasma 6 CPU/GPU temperature widget project; does not install or alter the desktop. |
| `create_script` | 2 | Create a private executable script; this tool does not execute it. |
| `create_symlink` | 2 | Create a new symlink to an existing approved writable target. File tools never follow links. |
| `create_systemd_user_service` | 2 | Create a new cachyos-mcp-NAME.service; does not enable or start it. |
| `disable_service` | 3 | Disable one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo. |
| `disable_systemd_user_service` | 2 | Disable an approved cachyos-mcp-* user service after confirmation. |
| `edit_file` | 2 | Replace approved file contents atomically, keeping a private backup first. |
| `enable_service` | 3 | Enable one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo. |
| `enable_systemd_user_service` | 2 | Enable an approved cachyos-mcp-* user service after confirmation. |
| `find_process` | 1 | Find process names containing a literal case-insensitive substring. |
| `get_boot_errors` | 1 | Errors and more severe journal messages for a boot. |
| `get_boot_time` | 1 | Boot timing summary and units delaying startup. |
| `get_cpu_info` | 1 | CPU topology and features, using lscpu JSON. |
| `get_disk_usage` | 1 | Usage of the root and home filesystems in bytes. |
| `get_environment_info` | 1 | Only desktop/session metadata; never dump the full environment. |
| `get_gpu_info` | 1 | PCI hardware and driver bindings (includes all graphics devices). |
| `get_kde_info` | 1 | Plasma version and standard configuration/package paths. |
| `get_kernel_info` | 1 | Kernel name, version, and release. |
| `get_listening_ports` | 1 | TCP/UDP listeners and visible owning processes, optionally filtered by port. |
| `get_memory_info` | 1 | RAM and swap amounts in bytes, from host /proc/meminfo. |
| `get_mounts` | 1 | Host mounted filesystems as findmnt JSON. |
| `get_network_info` | 1 | Host routing table as JSON. |
| `get_network_interfaces` | 1 | Interfaces, addresses, and link states as ip JSON. |
| `get_nvidia_status` | 1 | NVIDIA GPUs, driver, temperature, utilization, and VRAM usage. |
| `get_package_info` | 1 | Installed (-Qi) or repository (-Si) package metadata. |
| `get_plasma_version` | 1 | Installed Plasma version from host package metadata, without launching the desktop shell. |
| `get_process_details` | 1 | Selected /proc process status; no command line or environment secrets. |
| `get_service_status` | 1 | Selected service properties, excluding environment and command-line secrets. |
| `get_system_info` | 1 | Host OS release, architecture, hostname, and Python version. |
| `get_temperatures` | 1 | lm-sensors JSON readings; combine with get_nvidia_status for NVIDIA temperature. |
| `get_user_info` | 1 | Current unprivileged identity and groups. |
| `git_add` | 2 | Stage explicitly named regular project files; no directories, traversal, or pathspec magic. |
| `git_commit` | 2 | Commit already staged changes; hooks/signing are disabled and user identity must exist. |
| `git_diff` | 1 | Working tree diff with external diff programs and text conversion disabled. |
| `git_init` | 2 | Initialize Git in an existing approved project directory. |
| `git_log` | 1 | Recent commits inside an approved project. |
| `git_status` | 1 | Git status inside an approved project, with hooks and fsmonitor disabled. |
| `inspect_path` | 1 | Inspect metadata of an approved diagnostic path without following symlinks. |
| `inspect_plasma_configuration` | 1 | Inspect groups and setting names in known Plasma configuration, without changing it. |
| `install_package` | 3 | Install one administrator-allowlisted official repository package and its dependencies; requires enabled policy, explicit approval, and sudo authentication. |
| `list_failed_services` | 1 | Failed system or user services as systemctl JSON. |
| `list_installed_packages` | 1 | Installed package names and versions; optional literal substring filter. |
| `list_pci_devices` | 1 | Enumerate PCI devices and bound kernel drivers. |
| `list_processes` | 1 | Top processes by CPU; omit command lines that can contain secrets. |
| `list_running_services` | 1 | Running system or user services as systemctl JSON. |
| `list_usb_devices` | 1 | Enumerate USB devices. |
| `read_file` | 1 | Read a bounded, UTF-8, non-sensitive regular file in diagnostic roots. |
| `read_journal` | 1 | Bounded journal entries. Logs may contain sensitive application messages; review sharing. |
| `remove_package` | 3 | Remove one allowlisted package without cascading or recursive dependency removal. |
| `restart_service` | 3 | Restart one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo. |
| `restart_systemd_user_service` | 2 | Restart an approved cachyos-mcp-* user service after confirmation. |
| `search_packages` | 1 | Search configured official repositories without refreshing databases. |
| `start_service` | 3 | Start one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo. |
| `start_systemd_user_service` | 2 | Start an approved cachyos-mcp-* user service after confirmation. |
| `stop_service` | 3 | Stop one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo. |
| `stop_systemd_user_service` | 2 | Stop an approved cachyos-mcp-* user service after confirmation. |
