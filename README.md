<p align="center">
  <img src="assets/app-icon.png" width="128" alt="Lenovo LOQ Backlit Effects icon">
</p>

<h1 align="center">Lenovo LOQ Backlit Effects - Thrash</h1>

<p align="center">
  A native Windows lighting-effects studio for white-backlit Lenovo LOQ and compatible IdeaPad Gaming keyboards.
</p>

<p align="center">
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-38bdf8">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-22c55e">
  <img alt="Release v2.1.0" src="https://img.shields.io/badge/Release-v2.1.0-a855f7">
</p>

## What it does

Lenovo LOQ Backlit Effects controls the keyboard's global white backlight through Lenovo Vantage's installed `IdeaNotebookAddin` interface. It provides a modern native desktop UI, animated startup sequence, a battery-saving default mode, reactive typing modes, and two privacy-distinct music modes.

The application runs locally. It does not host a web server, send telemetry, or upload audio.

## Requirements

- Windows 10 or Windows 11, 64-bit
- A compatible Lenovo LOQ or IdeaPad Gaming laptop with a white backlit keyboard
- Lenovo Vantage and its `IdeaNotebookAddin` components installed
- Administrator access to communicate with Lenovo's hardware driver

Tested on a Lenovo LOQ with model identifier `83JC`. Other models may use different Vantage contracts and are not guaranteed.

## Download and install

1. Open the repository's [Releases](../../releases) page.
2. Download `LenovoLOQBacklitEffects-Thrash.exe`.
3. If the browser blocks the download, open its **Downloads** page (`Ctrl+J`), find the blocked EXE, and choose **Keep**, **Allow download**, or **Download unsafe file**. Confirm the warning only when the file came from this repository.
4. Optionally download `Thrash-Code-Signing.cer` and `SHA256SUMS.txt`.
5. Verify the SHA-256 checksum before running the application.
6. Double-click the EXE and accept the administrator prompt.

> Chrome and Edge may block uncommon self-signed applications automatically. The EXE must sometimes be allowed manually from the browser's Downloads page before it can be installed. This warning is expected for a self-signed release; always verify the checksum first.

The release is signed with a self-signed `CN=Thrash` certificate. A self-signed certificate is not automatically trusted on other computers. Import the included public `.cer` only if you trust this repository and the downloaded checksum matches the release notes. A publicly trusted publisher label requires a commercial CA-issued code-signing certificate.

## How to use

1. Start the application and wait for the LOQ-inspired opening animation.
2. Confirm the status row says **Lenovo bridge online**.
3. Select a lighting-mode card.
4. Adjust **Speed**. For music effects this control becomes **Sensitivity**.
5. Select **Start Mode**.
6. Optionally enable **Run at Windows Startup**. The app creates an elevated per-user Task Scheduler entry so it can start without a second UAC prompt at every sign-in.
7. Use **Light On / Off** for manual control or **Re-detect** if Lenovo Vantage was updated while the app was open.

Closing the application restores the keyboard to full brightness.

## Effects

| Effect | Behavior |
| --- | --- |
| Default Backlight | Normal bright backlight; sleeps after 10 idle seconds and wakes on the next keypress |
| Blink | Regular on/off lighting |
| Breathe | Off → dim → bright → dim cycle |
| Strobe | Rapid flashes; use carefully |
| Heartbeat | Double-pulse rhythm |
| SOS | Morse-code SOS sequence |
| Disco | Random fast flashes |
| Lightning | Irregular lightning strikes |
| Pulse | Bright crest followed by a fade |
| Candle | Uneven candle-style flicker |
| Binary Clock | Encodes the current seconds in six binary pulses |
| Wave | Rolling off/dim/bright brightness crest |
| Reactive | Changes brightness when keys are pressed |
| Music / Mic | Reacts to the default microphone level |
| Music / Speaker | Detects beat-like output transients without recording the microphone |

> The supported keyboard exposes one global lighting zone and three states: off, dim, and bright. A spatial left-to-right wave is therefore not possible.

## Music privacy

- **Music / Mic** opens the Windows default microphone and evaluates short audio blocks in memory. Nothing is saved or transmitted.
- **Music / Speaker** reads the normalized peak meter exposed by Windows Core Audio. Adaptive fast and slow envelopes isolate sudden beat-like attacks from sustained loudness. It does not record the microphone, capture speaker samples, or save audio.

## Battery saver and Windows startup

**Default Backlight** is the normal non-animated mode. It holds the keyboard at full brightness while you are active, switches the light off after 10 seconds without a keypress, and restores it on the next keypress.

**Run at Windows Startup** creates a per-user Task Scheduler entry named `Lenovo LOQ Backlit Effects - Thrash` with highest privileges. Disable the same checkbox to remove the task. The setting affects only this application and does not install a service.

## Why PowerShell appears in Task Manager

Lenovo's supported application interface is shipped as private .NET assemblies with Lenovo Vantage. The app maintains one hidden, non-interactive Windows PowerShell process to load those assemblies and send low-latency brightness commands.

There is no visible PowerShell window. If the helper is terminated, the application monitors it and automatically reconnects. See [Architecture](docs/architecture.md) for details.

## Build from source

```powershell
git clone <repository-url>
cd Lenovo-LOQ-Backlit-Effects-Thrash
py -m pip install -r requirements-build.txt
py -m PyInstaller --clean --noconfirm keyboard-effects.spec
```

The unsigned build is created at:

```text
dist\LenovoLOQBacklitEffects-Thrash.exe
```

`build_exe.bat` performs the same steps interactively. Local builds are unsigned unless you provide your own code-signing certificate. Never commit a `.pfx`, `.p12`, private key, or certificate password.

## Troubleshooting

See the dedicated [Troubleshooting guide](docs/troubleshooting.md) for Lenovo Vantage detection, audio devices, administrator access, and model compatibility.

## Contributing

Bug reports and compatibility results are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Please include the laptop model, Windows version, Lenovo Vantage version, and diagnostic output with personal information removed.

## Security and legal notice

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability. Lenovo, LOQ, Legion, IdeaPad, and Lenovo Vantage are trademarks of Lenovo. This independent project is not affiliated with, endorsed by, or supported by Lenovo. Lenovo proprietary DLLs are not distributed with this repository.

## License

The original code in this repository is available under the [MIT License](LICENSE). This license does not apply to Lenovo software, trademarks, drivers, or proprietary assemblies discovered on the user's computer.
