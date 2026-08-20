# Security Policy

## Supported version

Security fixes are applied to the latest release and the default branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature when available. Do not publish administrator-boundary issues, arbitrary command execution, certificate private material, or exploitable Lenovo driver behavior in a public issue before a fix is available.

Include:

- A clear impact statement
- Reproduction steps
- Affected version and Windows build
- Whether administrator privileges are required
- Suggested mitigation, if known

## Trust boundaries

The application:

- Runs as administrator to access Lenovo's hardware interface.
- Starts a hidden, non-interactive PowerShell helper with a fixed command path.
- Loads Lenovo Vantage assemblies from `C:\ProgramData\Lenovo\Vantage\Addins`.
- Installs a global keyboard hook only while the React effect is active.
- Opens the microphone only while Music · Mic is active.
- Reads the Windows render-endpoint peak only while Music · Speaker is active.

The project does not distribute Lenovo assemblies and does not intentionally collect or transmit telemetry.

## Release certificates

Published binaries may be signed with a self-signed Thrash certificate. The public `.cer` is safe to distribute; private keys, `.pfx` files, and passwords must never be committed or attached to a release.
