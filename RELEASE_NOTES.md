# Thrash Lightening Control v3.1.1

The God Mode release: a rebuilt lighting engine inside an original liquid-glass Windows interface.

## Highlights

- Stable 96 Hz Breathe renderer with a slower, soft-shouldered curve
- One-click effect switching and persistent top-right master power
- Animated Thrash wordmark, transparent glass surfaces, Light/Dark modes, and four accent themes
- Battery Saver starts dark at boot, breathes up on the first key, and sleeps after 30 seconds idle
- Clean normal mode with automatically tuned speeds and one recommended Reactive behavior
- God Mode reveals advanced timing, alternate Reactive behavior, and adjustable idle timeout
- Red scan-line God Mode unlock sequence
- Dedicated Lighting, Audio Reactive, Device, Settings, and About sections
- Speaker-output beat transients remain separate from microphone response
- Capability-first detection for compatible Lenovo LOQ white-backlit keyboards
- Tray persistence and Task Manager-visible Windows startup behavior

## Release assets

- `ThrashLighteningControl-Setup-v3.1.1.exe` — signed compressed Windows installer
- `SHA256SUMS.txt` — installer integrity checksum

## Hardware reality

Compatible keyboards expose only Off, Dim, and Bright. The app creates intermediate-looking intensity and smoother transitions by rapidly blending those native states. A single-zone keyboard cannot produce a spatial left-to-right wave.

Fn+Space is the Lenovo keyboard-light shortcut. Fn+Q controls performance/thermal mode and is left untouched.

## Security and privacy

Administrator access and Lenovo Vantage are required. Audio analysis stays local. Speaker mode uses the Windows output peak meter and does not record microphone or speaker samples.

The installer is signed using a self-signed `CN=Thrash` certificate. Browsers or Windows may warn because the certificate has no public reputation. Verify `SHA256SUMS.txt` before running the installer.
