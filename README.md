# cachyos-system

A working, local MCP server for inspecting and administering this CachyOS workstation. It uses the **official MCP Python SDK 2.3.0**, with 59 typed, structured tools over stdio. Claude Code, Codex and Gemini CLI each launch their own process using the same server, policy, and bounded audit log.

The project is installed in `/home/justin/Projects/cachyos-mcp`, with a host Python virtual environment, locked dependencies, automated security tests, real-machine diagnostic probes, and client registrations. Restart Claude Code, Codex or Gemini CLI to load the new server. Ask, for example, “Check my CPU and GPU temperatures” or “What is listening on port 8080?”

## Inspected environment

The implementation was checked on October 5, 2026 with CachyOS, kernel `7.2.9-1-cachyos`, Python 3.14.7, Plasma 6.7.5, NVIDIA GeForce RTX 5080 / driver 615.71.09, Claude Code 2.1.287, and Codex CLI 0.160.0. See [environment.json](config/environment.json) for host utility availability. Both `paru` and `yay` exist; AUR builds are deliberately outside the privileged tool interface.

VS Code runs in Flatpak, whose Python and OS utilities differ from the host. **Use `scripts/launch.sh`**, which detects Flatpak and runs the entire server through `flatpak-spawn --host`. Native terminals launch directly. This keeps `/proc`, `/etc`, systemd, pacman, sensors, and filesystem checks on the real host. The Python virtual environment was created on the host; running its interpreter directly inside Flatpak can select the runtime’s incompatible Python.

## Installation and verification

Already installed. To recreate the environment from a **host terminal**:

```sh
cd ~/Projects/cachyos-mcp
uv sync --locked --extra dev --extra gui
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/python scripts/smoke_test.py
```

Inside Flatpak, prefix host commands with `flatpak-spawn --host` and use absolute paths. Without uv, create the environment with host `python -m venv .venv` and install `-e '.[dev]'` using pip; `uv sync --locked` is the reproducible option. Runtime installations can omit `--extra dev`; keep `--extra gui` to use the settings app.

The launcher starts a stdio server and waits for an MCP client. It does not serve an HTTP port or install a background service. stdout belongs exclusively to MCP; server diagnostics go to stderr, and administration audit events go to disk. The server refuses to run as root.

Required Python dependencies are in [pyproject.toml](pyproject.toml) and [uv.lock](uv.lock). Native utilities include `pacman`, `systemctl`, `journalctl`, `systemd-analyze`, `lscpu`, `findmnt`, `ps`, `ip`, `ss`, `lspci`, `lsusb`, `sensors`, and `nvidia-smi`. Generated KDE artifacts were also checked with `desktop-file-validate`, `systemd-analyze --user verify`, and `qmlformat`. Missing utilities return `missing_executable` with a useful hint; nothing installs them automatically.

## Desktop settings application

Open **CachyOS Agent Settings** from KDE’s application menu, or run:

```sh
~/Projects/cachyos-mcp/scripts/settings.sh
```

The app now stays available in KDE’s **system tray** while running. Click its icon to open settings, or right-click for **Open settings**, **Hide settings window**, **Open documentation**, and **Quit**. The **Open console** submenu launches **Claude Code**, **Gemini CLI**, or **Codex** in a new Konsole window, starting in this agent’s project directory. Sessions remain independent of the settings app, retain normal client authentication/approval prompts, and stay open if the client exits so startup errors are readable. Missing clients or Konsole produce a clear dialog. Quit and reopen an already running tray app after updating its code to load new menu actions. Closing the settings window hides it to the tray and retains any unsaved draft. Quit is the explicit exit action and asks before discarding changes. If the desktop has no tray, the app uses normal window-close behavior.

To launch directly into the tray:

```sh
~/Projects/cachyos-mcp/scripts/settings.sh --tray
```

This option shows the normal window if a tray is unavailable. Start the app once per desktop session; login autostart is not configured. The tray manages the settings app; MCP clients continue to launch their own agent processes.

The native Qt app is installed with optional dependencies `PySide6` and `tomlkit`. It edits every policy setting through five pages: Overview, Allowed folders, Permissions & tools, Execution limits, and Logging. Folder pickers and manual path entry maintain project/writable roots; permissions include tool-group switches, user-change and privileged-operation switches, and package/service allowlists. The **Read-only draft** button disables both types of changes while retaining your diagnostic groups. Existing sudo and fixed server safety boundaries remain in force.

Changes stay in a draft until you choose **Save settings…** and review the proposed TOML diff. The app uses the server’s validated configuration model, preserves TOML comments, writes atomically, and checks the originally loaded file to detect external edits. Invalid package/service names, folder roots, log paths and limits are rejected. Missing service suffixes must be entered as full names such as `bluetooth.service`. Policies and backup paths cannot be symlinks; policy files with multiple hardlinks are rejected.

The five most recent pre-save versions are stored with private permissions in `config/.settings-backups/`, excluded from Git. **Restore backup…** and **Import policy…** load a draft for review; they never immediately replace the live policy. **Export draft…** writes a new TOML file and refuses to overwrite an existing file. **Reload from disk** discards a draft only after confirmation. **Secure defaults** stages the original default policy, including disabled privileges; it does not automatically save.

Restart Claude Code, Codex and Gemini CLI after a save so they reload the policy. The Overview displays client registration from their configuration files, not a live connection status. Client authentication, approval preferences and client-side timeouts remain owned by those clients and are not rewritten by the settings app. To edit an alternate policy, pass `--config /absolute/settings.toml` to the launcher.

The menu launcher is installed at `~/.local/share/applications/cachyos-agent-settings.desktop`; its source is [config/cachyos-agent-settings.desktop](config/cachyos-agent-settings.desktop). The Flatpak launcher runs the app on the host with a clean Qt plugin environment and the workstation’s Wayland platform. Both offscreen GUI tests and a real KDE Wayland window were verified without changing live permissions. GUI tests use temporary policy files; install the `gui` extra to run them.

## Client connections

The existing clients’ actual `mcp add --help` syntax was inspected before registration. Only a new `cachyos-system` entry was added. Previous client settings are backed up privately under `.state/client-backups/`, excluded from Git. Claude reported **Connected**; Codex reported the stdio entry **enabled**. The same launcher was exercised with the official SDK in modern and legacy MCP modes, including initialization, tool discovery, calls, and invalid argument rejection. A model-driven Codex conversation was not launched as part of testing.

Claude Code’s user registration, available across projects:

```sh
claude mcp add --transport stdio --scope user cachyos-system -- /home/justin/Projects/cachyos-mcp/scripts/launch.sh
claude mcp get cachyos-system
```

This updates `~/.claude.json`. For a project-scoped registration use `--scope project`; the corresponding shape is provided in [claude-mcp.json](config/claude-mcp.json). Use Claude’s `/mcp` command after restarting to inspect the connection and tool permissions.

Codex’s global registration:

```sh
codex mcp add cachyos-system -- /home/justin/Projects/cachyos-mcp/scripts/launch.sh
codex mcp get cachyos-system
```

This updates its user `config.toml` (normally `~/.codex/config.toml`, or the configured `CODEX_HOME`). The same configuration is shared with the Codex IDE extension. [codex-mcp.toml](config/codex-mcp.toml) shows the verified stdio table and optional timeouts. Use Codex’s `/mcp` command after restarting. Client permission prompts are separate from the server’s enforcement; review each proposed change rather than globally approving all mutation tools.

Remove only this server with `claude mcp remove cachyos-system -s user` or `codex mcp remove cachyos-system`. Re-registering does not require restoring unrelated client settings.

Gemini CLI 0.62.0 is now installed locally under `.clients/gemini`, pinned by `package.json` and `package-lock.json`. Run `gemini` from a host terminal, or use the Flatpak-safe project launcher:

```sh
~/Projects/cachyos-mcp/scripts/gemini.sh
```

On first run, approve this project folder in Gemini’s trust dialog and complete Google sign-in interactively. The agent connection is already registered in `~/.gemini/settings.json` using the installed CLI’s verified syntax:

```sh
gemini mcp add --scope user --transport stdio --timeout 45000 cachyos-system /home/justin/Projects/cachyos-mcp/scripts/launch.sh
gemini mcp list
```

`gemini mcp list` checks the local connection after authentication and folder trust, without launching a model conversation. Registration was verified, but Gemini currently requires interactive authentication and project-folder approval before the live connection check can complete. From a host terminal, run `cd ~/Projects/cachyos-mcp` then `gemini`; choose **Trust folder** for this project rather than trusting an entire parent tree. After signing in, use `/mcp` inside Gemini to inspect available tools. The registration does **not** use `--trust`; Gemini’s normal action confirmations remain enabled, alongside the agent’s path policy, confirmation arguments and privilege boundary. Gemini appears in the settings app’s Overview. Restart it after policy changes. Client settings and authentication files under `~/.gemini` are protected from the agent’s filesystem tools.

[gemini-mcp.json](config/gemini-mcp.json) provides the supported configuration shape. Reinstall the pinned CLI with host `npm ci --prefix ~/Projects/cachyos-mcp/.clients/gemini`. The `~/.local/bin/gemini` launcher forwards to this project without a global npm install or root access. Remove just its agent registration with `gemini mcp remove --scope user cachyos-system`. Google account authentication stays with Gemini and is not handled by this project’s GUI.

Official references: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Codex MCP documentation](https://developers.openai.com/codex/mcp), [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp), [Gemini CLI MCP documentation](https://geminicli.com/docs/tools/mcp-server/), and [KDE widget setup](https://develop.kde.org/docs/plasma/widget/setup/).

## Permissions and configuration

Policy lives in [config/settings.toml](config/settings.toml). The user edits policy directly and restarts MCP clients to reload it; tools cannot edit their own policy. Unknown configuration fields, invalid limits, and unknown groups are rejected at startup.

| Level | Capabilities | Required boundary |
| --- | --- | --- |
| 1 | System, hardware, process, network, package, service, journal, KDE and file inspection; safe Git reads | No confirmation argument; OS read permissions still apply |
| 2 | File creation/editing, scripts, directories, constrained symlinks, launcher/widget generation, managed user services, Git init/add/commit | Explicit user approval followed by strict JSON `confirmed: true`; writable/project allowlists |
| 3 | Install/remove approved official packages; enable/disable/start/stop/restart approved system services | Level 2 confirmation plus administrator `privileged_enabled = true`, exact allowlists, and authenticated `sudo -n` |

**User-level changes can be disabled separately with `user_changes_enabled = false`.** For read-only administration, also leave `privileged_enabled = false`; tool groups can remain enabled for diagnostics.

**Privileged operations default to disabled.** Only `blender` and `bluetooth.service` are initially allowlisted. To intentionally use these tools, manually enable `privileged_enabled`, review the package/service allowlists, and restart the client. Installation uses `pacman -S --needed --noconfirm --noprogressbar` after explicit approval, including any required dependencies. Removal uses `-R`, without recursive or cascading removal. No AUR helper runs as root and package databases are not automatically refreshed.

Authentication remains governed by existing sudo policy. The server never collects passwords, presents an unrestricted root command interface, modifies sudoers, or enables passwordless sudo. If noninteractive authentication fails, it returns `authentication_required`; use a host terminal to authenticate or perform the exact displayed action there. A cached `sudo -v` may not apply under policies that bind credentials to a TTY. Do not weaken that policy to accommodate MCP.

The default command timeout is 30 seconds. For package transactions, choose a suitable `max_command_timeout` (for example 600) **and increase the client’s `tool_timeout_sec` beyond it** before approving the install. Timeouts or cancellation can interrupt a transaction or leave privileged descendants finishing independently; inspect pacman state before retrying. Prefer a terminal for long upgrades or package operations needing human interaction. This project never runs a full system upgrade.

Configuration controls:

| Setting | Default / meaning |
| --- | --- |
| `allowed_project_directories` | `~/Projects`; Git and generated widget projects must be within these roots |
| `allowed_writable_directories` | `~/Projects`, `~/.config`, `~/.local`; roots must be inside home, not the entire home |
| `enabled_tool_groups` | system, hardware, processes, network, packages, systemd, journal, filesystem, kde, development, privileged; removed groups are not advertised |
| `user_changes_enabled` | true; disable to hide all level 2 mutation tools while keeping inspection tools |
| `privileged_enabled` | false |
| `allowed_packages`, `allowed_services` | exact, administrator-owned allowlists |
| `max_command_timeout` | 30 seconds; validated range 1–3600 |
| `max_output_size` | 65536 bytes across stdout and stderr per command |
| `max_file_size` | 262144 bytes per file read/write |
| `logging_level` | INFO; SDK diagnostic verbosity, audit is always enabled |
| `log_directory` | this project’s private `.state` directory |
| `log_max_bytes`, `log_backups` | 1 MiB per audit file, three rotated backups |

Run with a different policy using host `.venv/bin/python -m cachyos_mcp.server --config /absolute/policy.toml`; adjust the client args accordingly. The active policy path and configured log directory are also protected from file tools.

## Tools and structured results

See the complete [59-tool catalog](docs/tools.md) and exact [input/output schemas](docs/tool-schemas.json), generated from `tools/list`.

Diagnostics cover host/kernel/CPU/memory/disks/mounts, GPU/NVIDIA/temperatures/USB/PCI, interfaces/routes/ports, processes, installed/repository packages, system and user service status, running/failed units, journals and boot timing, user/session metadata, and KDE configuration locations.

Command tools return `success`, argv `command`, `exit_code`, bounded `stdout` and `stderr`, `duration_ms`, and `truncated`, with parsed `data` where practical. Native inspections return `success` and structured `data`. Expected denial and resource errors return `success: false` plus `error` and an actionable message or hint. Malformed MCP arguments are protocol-valid error tool results. Output-limit results are explicitly incomplete, not silently presented as complete data.

Memory values are in bytes; GPU output labels its temperature, utilization, and VRAM units. Network interfaces/routes and mounted filesystems use native JSON; service properties, listeners, and process lists have named fields. Process inspection omits command lines and environment strings that often contain credentials. Environment inspection uses a small desktop/session allowlist. Package queries do not change the machine.

## Files, KDE, services, and Git

File tools require absolute paths (or `~/...`), without `..`. `create_file` never overwrites; `edit_file` reads a bounded regular single-link file, creates a private `.backup-<unique-id>` first, then atomically replaces it. Config edits receive the same backup protection. Review and remove old backups manually as appropriate.

Descriptor-relative traversal uses `O_NOFOLLOW` for every directory component, including the final file. Symlinks cannot redirect writes, and hardlinked existing files cannot be edited. Writable-root siblings and the root directories themselves are denied. `create_symlink` accepts only an existing approved writable target; other file tools still do not follow the resulting link. Read tools use approved diagnostic roots (`home`, `/etc`, `/var/log`, `/usr/share`) and regular-file limits. `inspect_path` reports leaf symlink metadata without dereferencing it.

Server source, virtual environment, launcher, policy, and audit files are protected. Credential directories and names (SSH/GPG/cloud credentials, wallet/keyring stores, environment secret files), Git metadata, client policies, shell startup files, and automatic-start configuration are blocked. These filename checks are conservative exclusions, **not a promise that arbitrary application data contains no secrets**. Journal messages and explicitly requested file contents may contain private information; their content is never copied into audit logs.

`create_script` writes an executable file but does not run it. `create_desktop_entry` creates a new launcher in `~/.local/share/applications`, validates an absolute executable and bounded argv, and escapes Desktop Entry arguments and field codes. It never launches the application.

`create_systemd_user_service` creates `~/.config/systemd/user/cachyos-mcp-NAME.service`, with literal argument escaping, `Type=exec`, and restart-on-failure. It does not start or enable it. The five user-service action tools accept only `cachyos-mcp-*` units with approved local files, reload user systemd configuration, and perform the confirmed action. Existing unrelated user services are inspected with read-only systemd tools.

`create_plasma_widget_project` creates a fresh project with Plasma 6 `metadata.json`, `contents/ui/main.qml`, and a README. It displays live CPU/GPU temperature through the installed KSysGuard sensor module, with explicit “Unavailable” states. The default IDs `cpu/all/averageTemperature` and `gpu/gpu0/temperature` were verified against this host’s `org.kde.ksystemstats1` interface. Other systems can supply their IDs as tool arguments. No widget is installed and no desktop layout is changed during generation. Review the project, then install it in a host terminal with `kpackagetool6 --type Plasma/Applet --install .` and add it using Plasma’s Add Widgets menu. GUI placement/rendering was not automatically exercised.

`inspect_plasma_configuration` reports groups and setting names in known KConfig files, helping locate settings without changing them. If an approved config file needs editing, use `read_file` and `edit_file` after reviewing the change; a backup is retained. Plasma may rewrite settings while running, so consider the relevant application’s state before editing.

Git tools support status, diff, log, init, explicit-file staging, and committing staged changes within approved projects. They disable hooks, fsmonitor, signing, external diff/text conversion, global/system Git configuration, and submodule traversal; pin the worktree; reject metadata symlinks and repository-defined filters for write operations; and reject traversal or pathspec magic. Linked Git worktrees (`.git` files), repositories with over 10000 metadata entries, clone/push/pull, destructive resets, deletion staging, and credential handling are unsupported. Commit identity must already exist in the repository’s local configuration. Scripts, launchers, user services, and Git commits can encode user-level behavior, so their approval should include reviewing the actual content.

## Diagnostics to try

- **Temperature:** `get_temperatures` plus `get_nvidia_status`.
- **Slow boot:** `get_boot_time`, `get_boot_errors`, relevant `read_journal` calls.
- **Failed services:** `list_failed_services`, `get_service_status(name)`, `read_journal(unit=name)`; use `user=true` for user services.
- **Port 8080:** `get_listening_ports(port=8080)`, then `get_process_details(pid)` for visible owners.
- **Bluetooth:** service status, unit journal, USB/PCI enumeration, and installed package filtering. A confirmed restart is available only after deliberate privileged-policy enablement and authentication.
- **NVIDIA:** GPU/driver status, PCI driver binding, kernel info, and boot error logs.
- **Application login startup:** generate a user service, inspect its file, then separately approve enable/start.

Tools provide facts and controlled actions. AI reasoning stays in the client; diagnostic output is untrusted data and must not be treated as instructions.

## Audit, security, and unsupported operations

`.state/audit.jsonl` records UTC timestamps, known tool names, redacted argument fields, permission levels, sanitized command details, success/failure, exit status, and duration. Numeric/boolean diagnostic parameters are retained; paths, content, free text, and command argument values are redacted. Command output, environment, passwords, tokens, keys, and file contents are not logged. Request middleware also audits malformed and unknown tool calls without preserving arbitrary supplied tool names.

An intent audit event is written before side effects; audit failure prevents execution. Rotation uses a process-shared lock so simultaneous client processes share the same bounded files. Directory permissions are 0700 and files are 0600. At defaults, audit storage is bounded to roughly four MiB; client backups are separate files. This is a local user-owned audit trail, not a tamper-proof record against the workstation owner.

The only subprocess layer is `executor.py`: argv arrays, no shell, minimal child environment, fixed host utility PATH, DEVNULL stdin, separate process groups, timeouts, cancellation cleanup, output limits, missing-command handling, and structured status. Client-requested commands cannot choose an arbitrary executable or supply raw root argv. `confirmed=true` is a client assertion of approval, **not independent proof of a human decision**; use the client’s approval controls and trust only intended local clients. No network listener is exposed.

Formatting, partition changes, raw disk writes/dd, recursive deletion, arbitrary root shells, bootloader/Secure Boot/sudoers edits, security-control changes, arbitrary kernel-module manipulation, and arbitrary system config edits have no tools. `modify_approved_system_config` is intentionally not provided until a specific target and validated schema are designed. Unsupported requests must be refused rather than reconstructed using other capabilities.

## Troubleshooting

- **SDK import errors / Python ABI mismatch:** recreate using host `uv sync --locked`. Inside Flatpak use the launcher rather than directly invoking `.venv/bin/python`.
- **Flatpak host access denied:** the client environment must already allow `flatpak-spawn --host`; use a native host client if unavailable. This project does not change Flatpak permissions.
- **Tool absent:** inspect `enabled_tool_groups`, then restart the client.
- **Missing utility:** the error names it; install the corresponding host package separately after approval.
- **Service or journal permission error:** only the current user’s existing read access applies. No group membership changes or root fallback happen automatically.
- **Path denied:** check the relevant root, protected path names, parent symlinks, and whether the path points into this protected server project.
- **Output limit:** reduce query limits, filter by unit/package/process/port, or deliberately adjust the administrator output limit. stdout/stderr are capped together.
- **User service action denied:** use the generated `cachyos-mcp-*` service name and ensure its local unit is a regular approved file.
- **Privileged action refused:** inspect policy, confirmation, allowlists, and existing sudo authentication; root actions are never retried through arbitrary shell commands.
- **Widget “Unavailable”:** confirm the sensor IDs in KDE System Monitor and inspect `plasma-ksystemstats.service` using `user=true`.
- **Plasma version:** read from the `plasma-workspace` package rather than launching `plasmashell`, which failed under the restricted subprocess environment on this host.

## Architecture, tests, and expansion

`server.py` creates the official SDK server and registers modules. `config.py` validates policy; `security.py` validates identifiers and anchors file operations; `executor.py` owns subprocess execution; `logging_config.py` handles private, bounded JSON auditing; `runtime.py` enforces strict raw MCP argument schemas and tool/audit dispatch. The `tools/` modules split system, hardware, processes, network, packages, systemd, journal, filesystem, KDE, user services, development, and privileges.

Tests cover injection and invalid package/service names, traversal and sibling prefixes, protected and allowed paths, parent/leaf symlinks, hardlinks, backups, confirmation and strict MCP types, unknown fields/groups, subprocess timeouts/output bounds, missing executables, audit redaction/rotation, Git filters/metadata links, generated desktop/unit/QML validation, privilege defaults/allowlists/authentication, and real modern/legacy stdio reads. Temporary generated artifacts are tested without changing the live desktop or services. Privileged actions use a fake executor; no privileged OS mutation is used for verification.

Initial server validation passed **52 automated tests**, lint/format checks, and all smoke checks. The separate smoke script exercises 31 read-only tools over the installed launcher, including every diagnostic category. Git history records phases 1–5 and the final integration milestone, after each phase’s tests passed.

To add a tool, use a focused module and `@runtime.tool('group', level)` with concrete parameter types, a useful docstring, and `dict[str, Any]` structured output. Validate identifiers and use `runtime.run` for fixed internal argv or `runtime.paths` for files. Add the module to `MODULES`, update group policy if needed, add meaningful security tests, and regenerate the tool schemas/catalog. Level 2/3 mutations need `confirmed: StrictBool` and `security.confirm`; privileged expansion requires a new exact allowlist or a purpose-built validated action, never a model-supplied root command.

The settings-app milestone passed **62 tests**, including all prior agent checks, GUI control coverage, validation, permission gating, comment preservation, save/reload/import behavior, backup rotation, symlink rejection and external-edit conflicts.

The Gemini integration milestone passed **68 tests**, including registration-status handling and protection of Gemini settings/authentication paths. The installed CLI version and configuration were verified; its live health check is pending the user’s interactive sign-in and folder trust.

The tray milestone passed **71 tests**. Live KDE verification confirmed StatusNotifier registration, close-to-tray and click-to-open without modifying policy.

The tray console milestone passed **76 tests**. Native KDE checks opened each client in Konsole with a version-only command and verified successful terminal exits, without starting model conversations. Console launches use fixed client choices and argv arrays through the central execution layer.
