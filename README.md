<p align="center">
  <img src="assets/app-icon.png" width="128" alt="Lenovo LOQ Backlit Effects icon">
</p>

<h1 align="center">Lenovo LOQ Backlit Effects - Thrash</h1>

<p align="center">A native Windows lighting lab for compatible Lenovo LOQ white-backlit keyboards.</p>

<p align="center">
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-38bdf8">
  <img alt="Release v3.1.1" src="https://img.shields.io/badge/Release-v3.1.1-ef4058">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-22c55e">
</p>

## What v3.1.1 does

The app controls the keyboard's global white backlight through Lenovo Vantage's installed `IdeaNotebookAddin` interface. It is a real native desktop application: no localhost page, browser server, telemetry, cloud account, or audio upload.

- Original Legion Space-inspired navigation with liquid-glass depth and a Thrash background
- Battery Saver that starts dark at Windows sign-in, breathes up on the first key, and sleeps after 30 idle seconds
- Fluid 60 Hz Breathe curve and 1–100 perceived intensity control
- Streamlined Reactive mode with tuned timing automatically selected
- Separate Music / Mic and Music / Speaker modes; Speaker uses Windows output and adaptive beat-onset detection
- Optional God Mode that reveals speed, reactive variants, and the Battery Saver timeout after a red unlock animation
- System-tray operation, Task Manager-visible startup entry, diagnostics, privacy information, and clean uninstall

The keyboard hardware exposes only Off, Dim, and Bright. Intermediate intensities and smoother fades are created with fast pulse-density blending. Results can vary slightly by keyboard firmware.

## Requirements

- 64-bit Windows 10 or Windows 11
- A Lenovo laptop with a compatible single-zone white-backlit keyboard
- Lenovo Vantage with the `IdeaNotebookAddin` components installed
- Administrator access for the Lenovo hardware bridge

Compatibility is detected from Lenovo Vantage's backlight capability rather than a hard-coded model number. RGB keyboards and unsupported contracts are rejected safely.

## Download and install

1. Open the repository's [Releases](../../releases) page.
2. Download `LenovoLOQBacklitEffects-Thrash-Setup-v3.1.1.exe` and `SHA256SUMS.txt`.
3. If Chrome, Edge, or another browser blocks the installer, open the browser's **Downloads** page (`Ctrl+J`), locate the blocked file, and choose **Keep**, **Allow download**, or **Download unsafe file**. Only allow it when it came from this repository.
4. Verify the installer's SHA-256 value against `SHA256SUMS.txt`.
5. Run the installer and accept the Windows administrator prompt.

The compressed installer contains the application, public Thrash certificate, verification notes, checksum, README, license, shortcuts, and uninstaller. It does not silently add the self-signed certificate to a trusted store.

The release is Authenticode-signed with a self-signed `CN=Thrash` certificate. Windows may still display an unknown-publisher or reputation warning on another PC. A universally trusted publisher label requires a commercial CA-issued certificate.

## How to use

1. Open the app and confirm the header says **Lenovo bridge online**.
2. Choose a mode under **Lighting** or **Audio Reactive**.
3. Choose the desired **Intensity** from 1–100 and select **Start Mode**.
4. Leave God Mode off for curated automatic timing. Enable it in **Settings** only when you want advanced speed, reactive, or idle-timeout controls.
5. Closing the window keeps the app in the notification area by default. Use the tray menu's **Quit** command to exit fully.

`Fn+Space` is Lenovo's keyboard-backlight shortcut on supported LOQ models. Battery Saver watches the resulting native backlight state and synchronizes its remembered level when possible. `Fn+Q` controls Lenovo operating/thermal modes and is not intercepted by this app.

## Modes

| Mode | Behavior |
| --- | --- |
| Battery Saver | Soft wake to the selected intensity; off after 30 seconds idle |
| Breathe | Continuous sine-eased breathing with temporal intensity blending |
| Heartbeat | Double-pulse rhythm |
| Disco | Random high-energy pattern |
| Pulse | Fast rise and controlled fade |
| Binary Clock | Encodes the current seconds in six pulses |
| Wave | Asymmetric rolling brightness crest for a single-zone keyboard |
| Reactive | Dim idle, bright keypress, smooth release; stays active while held |
| Music / Mic | Follows energy from the default microphone locally |
| Music / Speaker | Reacts to beat-like transients from Windows speaker output, not the microphone |

Blink, Strobe, SOS, Lightning, and Candle were removed in v3.1.1 to keep the standard experience focused. Speed and alternate Reactive behaviors are hidden unless God Mode is enabled.

## Battery Saver, startup, and tray

When launched by Windows startup, the keyboard begins off. Battery Saver runs quietly in the tray and the first keypress breathes the light up to the user's remembered 1–100 intensity. After 30 seconds without keyboard input, it fades out again. The timeout can be changed only in God Mode.

**Run at Windows Startup** creates a current-user Startup apps entry and an elevated on-demand scheduled task named `Lenovo LOQ Backlit Effects - Thrash`. This avoids leaving a visible console window and lets the entry appear in Task Manager. Turning the option off removes both entries. No Windows service is installed.

## Audio privacy

- Music / Mic analyzes short microphone blocks in memory. Nothing is saved or transmitted.
- Music / Speaker reads the Windows Core Audio output peak meter. It does not open the microphone, record speaker samples, or upload audio.

## Why PowerShell appears in Task Manager

Lenovo exposes this backlight interface through private .NET assemblies installed with Lenovo Vantage. The app keeps one hidden, non-interactive Windows PowerShell helper alive to load those assemblies and send low-latency commands. Closing or killing that helper interrupts hardware control; the app attempts to reconnect automatically. See [Architecture](docs/architecture.md).

## Build from source

```powershell
git clone https://github.com/Thrash-PRX/Lenovo-LOQ-Backlit-Effects-Thrash.git
cd Lenovo-LOQ-Backlit-Effects-Thrash
py -m pip install -r requirements-build.txt
py -m PyInstaller --clean --noconfirm keyboard-effects.spec
```

For the compressed installer, install Inno Setup 6 and run `build_installer.bat`. Public certificates may be distributed; never commit a `.pfx`, `.p12`, private key, or password.

## Help and contributing

See [Troubleshooting](docs/troubleshooting.md), [Contributing](CONTRIBUTING.md), and [Security](SECURITY.md). Compatibility reports should include the laptop model, Windows version, Lenovo Vantage version, and copied diagnostics with personal information removed.

Lenovo, LOQ, Legion, IdeaPad, and Lenovo Vantage are trademarks of Lenovo. ASUS, TUF, and Armoury Crate are trademarks of their respective owners. This independent project is not affiliated with or endorsed by those companies, and it does not redistribute Lenovo proprietary DLLs.

Original project code is available under the [MIT License](LICENSE).
