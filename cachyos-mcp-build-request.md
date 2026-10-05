# Project: CachyOS System Control MCP Server

I want you to build a complete MCP (Model Context Protocol) server that allows AI coding agents such as Claude Code and Codex to inspect, diagnose, configure, and manage my CachyOS Linux computer.

You are working directly on my CachyOS machine, so you may inspect the system to determine paths, installed software, available commands, KDE configuration, Python version, package manager configuration, systemd setup, NVIDIA configuration, and other information necessary to implement the project correctly.

Do not merely give me instructions or sample code. Create the project, files, configuration, virtual environment, dependencies, and documentation yourself. Test the MCP server and fix problems you encounter.

## Environment

My system is:

- CachyOS / Arch Linux
- KDE Plasma
- fish is my normal interactive shell
- NVIDIA GPU
- systemd
- pacman
- AUR helper may be available
- VS Code
- Claude Code
- Codex
- Python is available

Before making assumptions, inspect the machine.

Create the project in:

~/Projects/cachyos-mcp

Use Python unless there is a compelling technical reason to use something else.

Use the current official MCP Python SDK and current MCP conventions. Do not implement a fake or proprietary approximation of MCP.

## Main Objective

Build a reusable MCP server named something similar to:

cachyos-system

The server should expose carefully designed tools that allow an AI agent to perform Linux administration tasks.

The design must prioritize:

1. Safety
2. Useful diagnostic information
3. Structured output
4. Explicit privilege boundaries
5. Input validation
6. Logging
7. Easy expansion
8. Compatibility with multiple MCP clients

Claude Code and Codex should ultimately be able to connect to the same MCP server.

## Permission Architecture

Implement three permission levels.

### Level 1: Read-Only Operations

These should generally execute without confirmation because they do not modify the machine.

Create MCP tools covering functionality such as:

- get_system_info
- get_kernel_info
- get_cpu_info
- get_memory_info
- get_disk_usage
- get_mounts
- get_gpu_info
- get_nvidia_status
- get_temperatures
- get_network_info
- get_network_interfaces
- get_listening_ports
- list_processes
- find_process
- get_process_details
- list_usb_devices
- list_pci_devices
- list_installed_packages
- search_packages
- get_package_info
- get_service_status
- list_failed_services
- list_running_services
- read_journal
- get_boot_errors
- get_boot_time
- get_user_info
- get_environment_info
- get_kde_info
- get_plasma_version
- inspect_path

Use native Linux utilities where appropriate, including things such as:

- systemctl
- journalctl
- pacman
- sensors
- nvidia-smi
- lspci
- lsusb
- ip
- ss
- df
- free
- ps
- lsblk

Do not assume every utility exists. Detect missing dependencies and return a useful structured error.

## Level 2: User-Level Changes

Implement controlled tools for operations that normally do not require root access.

Examples:

- create_file
- edit_file
- create_directory
- create_symlink
- create_script
- create_desktop_entry
- create_systemd_user_service
- enable_systemd_user_service
- disable_systemd_user_service
- start_systemd_user_service
- stop_systemd_user_service
- restart_systemd_user_service
- create_plasma_widget_project
- inspect_plasma_configuration
- manage files under ~/.config
- manage files under ~/.local
- manage files inside ~/Projects
- Git operations inside approved project directories

File operations need strong path validation.

Never allow path traversal or deceptive paths to bypass restrictions.

Prefer allowlisted directories rather than unrestricted filesystem writes.

## Level 3: Privileged Operations

Privileged operations must be much more restricted.

Potential tools include:

- install_package
- remove_package
- enable_service
- disable_service
- start_service
- stop_service
- restart_service
- modify_approved_system_config

DO NOT give the MCP server arbitrary unrestricted root shell access.

DO NOT configure unrestricted passwordless sudo.

DO NOT create something equivalent to:

sudo <arbitrary model supplied command>

Privileged operations must use explicit allowlisted actions with strict argument validation.

For example:

install_package("blender")

is acceptable.

An interface like:

execute_root_command("whatever the AI wants")

is NOT acceptable.

If privileged actions require interactive authentication, preserve that security boundary instead of weakening sudo security.

Design privileged functionality so additional operations can safely be added later.

## Shell Execution Security

Create one central execution layer rather than scattering subprocess calls throughout the project.

Requirements:

- Avoid shell=True whenever possible.
- Pass commands as argument arrays.
- Validate all externally supplied arguments.
- Add execution timeouts.
- Capture stdout.
- Capture stderr.
- Capture exit status.
- Handle missing executables.
- Handle timeouts.
- Limit output size.
- Prevent command injection.
- Log operations.
- Return structured results.

Where possible return data similar to:

{
  "success": true,
  "command": "...",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 123
}

Do not expose secrets in logs.

## Dangerous Operations

Explicitly block dangerous operations unless we intentionally design a safe implementation later.

Examples include:

- disk formatting
- partition deletion
- raw disk writes
- arbitrary dd
- arbitrary rm -rf
- arbitrary root shell
- changing bootloader configuration
- changing Secure Boot configuration
- deleting system directories
- changing sudoers
- disabling major security controls
- destructive filesystem operations
- arbitrary kernel module manipulation

The MCP server should refuse unsupported dangerous requests instead of trying to creatively work around its restrictions.

## Audit Logging

Implement an audit log.

Record things such as:

- timestamp
- MCP tool invoked
- sanitized arguments
- permission level
- command executed
- success/failure
- exit code
- execution duration

Do not log:

- passwords
- authentication tokens
- API keys
- private SSH keys
- environment secrets

Store logs somewhere sensible under the user's home directory.

Implement log rotation or otherwise prevent unlimited log growth.

## Configuration

Create a configuration file allowing me to control things such as:

- allowed project directories
- allowed writable directories
- enabled tool groups
- privileged operations enabled/disabled
- maximum command timeout
- maximum output size
- logging level

Use sensible secure defaults.

Privileged operations should default to the safer configuration.

## Architecture

Keep the project modular.

A reasonable structure might resemble:

cachyos-mcp/
    README.md
    pyproject.toml
    config/
    src/
        cachyos_mcp/
            server.py
            config.py
            executor.py
            security.py
            logging_config.py
            tools/
                system.py
                hardware.py
                processes.py
                network.py
                packages.py
                systemd.py
                journal.py
                filesystem.py
                kde.py
                development.py
                privileged.py
    tests/

You may improve this architecture if you have a better design.

Do not put the entire MCP server into one giant Python file.

## Structured Results

Where practical, parse command output and return structured information rather than giant blobs of terminal text.

For example, get_memory_info should ideally return values such as:

{
  "total": ...,
  "used": ...,
  "available": ...,
  "swap_total": ...,
  "swap_used": ...
}

Likewise, process, network, package, GPU, disk, and service information should be structured when reasonably possible.

Raw command output may also be included when useful.

## KDE Plasma Support

Because this is a KDE Plasma workstation, include useful Plasma-related capabilities.

The MCP should eventually make requests like these possible:

"Create a Plasma widget showing my CPU and GPU temperature."

"Create a desktop launcher for this program."

"Inspect my Plasma configuration."

"Find where this KDE setting is stored."

"Create a systemd user service that launches this application when I log in."

Do not blindly overwrite Plasma configuration files.

Back up configuration before potentially disruptive modifications.

## Diagnostic Workflows

Design individual tools so an AI agent can combine them to investigate problems.

For example, for:

"Why isn't Bluetooth working?"

the agent should be able to use tools corresponding to:

get_service_status("bluetooth")
read_journal("bluetooth")
list_usb_devices()
list_pci_devices()
list_installed_packages()

The MCP should provide facts and controlled actions rather than embedding lots of AI reasoning inside the MCP server itself.

## Tests

Create automated tests for important security behavior.

At minimum test:

- command injection attempts
- path traversal attempts
- invalid package names
- invalid service names
- blocked filesystem locations
- allowed filesystem locations
- command timeout handling
- excessive output handling
- malformed MCP arguments

Security tests are particularly important.

## Documentation

Create a thorough README explaining:

- what the MCP server does
- architecture
- installation
- virtual environment setup
- dependencies
- configuration
- available MCP tools
- permission levels
- security model
- logging
- troubleshooting
- adding new tools

Also document how to connect the MCP server to:

1. Claude Code
2. Codex

Before writing configuration for either client, inspect the versions installed on this machine and use the configuration format actually supported by those versions.

Do not invent configuration syntax.

## Installation

Set the project up completely.

If appropriate:

1. Create ~/Projects/cachyos-mcp
2. Create a Python virtual environment.
3. Install dependencies.
4. Create the project structure.
5. Implement the MCP server.
6. Run tests.
7. Start the MCP server locally.
8. Verify MCP initialization.
9. Verify several read-only tools.
10. Configure Claude Code to access it.
11. Configure Codex to access it if practical.

Do not modify unrelated system configuration.

## Development Strategy

Build this incrementally.

Phase 1:
- MCP server foundation
- configuration
- secure command executor
- audit logging
- read-only system tools

Test it.

Phase 2:
- process/network/package/systemd/journal tools

Test it.

Phase 3:
- safe filesystem and user-level modification tools

Test it, especially path restrictions.

Phase 4:
- KDE/Plasma tools
- systemd user-service tools
- development/Git helpers

Test it.

Phase 5:
- carefully controlled privileged operations

Do not weaken system security just to make privileged operations convenient.

Phase 6:
- Claude Code integration
- Codex integration
- final end-to-end testing

Commit meaningful milestones to Git so changes can be rolled back.

## Important Behavior

You are authorized to create and modify files inside:

~/Projects/cachyos-mcp

You may inspect the rest of the system as necessary.

Before modifying files outside the project directory, determine whether the modification is actually necessary.

Do not:

- alter unrelated user files
- uninstall existing software unnecessarily
- change my desktop configuration without a clear reason
- weaken sudo
- expose credentials
- disable security mechanisms
- perform destructive operations

If something requires elevated privileges or my explicit interaction, stop at that specific step and tell me exactly what needs approval.

Otherwise, continue working autonomously.

## Final Goal

When finished, I want to be able to open Claude Code or Codex and ask things like:

"Check my CPU and GPU temperatures."

"Why did my computer boot slowly?"

"Check for failed systemd services and investigate them."

"What's using port 8080?"

"Check whether my NVIDIA drivers are functioning correctly."

"Create a systemd user service for this Python application."

"Create a KDE desktop launcher for this program."

"Create a Plasma widget showing CPU and GPU temperatures."

"Install Blender."

"Restart Bluetooth."

The agent should be able to inspect the real machine through MCP, diagnose problems, and perform explicitly permitted actions while retaining strong safety boundaries.

Begin by inspecting the environment and installed MCP clients. Then create the project and implement Phase 1. Continue through subsequent phases only after the tests for the current phase pass.