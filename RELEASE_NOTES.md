# Lenovo LOQ Backlit Effects - Thrash v2.1.0

A sharper interface, beat-focused speaker lighting, and automatic battery saving.

## Highlights

- Redesigned typography, capitalization, lighting cards, and Thrash brand mark
- New Default Backlight mode with no animation
- Automatic backlight sleep after 10 idle seconds
- Immediate wake on the next keyboard input
- Run at Windows Startup toggle using an elevated per-user scheduled task
- Adaptive speaker beat detection based on transient onsets instead of raw volume alone
- Microphone and speaker modes remain separate and clearly labeled

## Release assets

- `LenovoLOQBacklitEffects-Thrash.exe` — signed standalone Windows application
- `Thrash-Code-Signing.cer` — public self-signed certificate
- `SHA256SUMS.txt` — release integrity checksums

## Important

Administrator access is required. Lenovo Vantage must be installed, and compatibility varies by laptop model. The keyboard offers one global white lighting zone, so effects use the off, dim, and bright states available from the hardware.

Speaker beat mode uses the Windows output endpoint peak meter. It detects sudden output transients but does not record the microphone, capture speaker samples, or distinguish individual frequency bands.

The Thrash certificate is self-signed. Import it only after verifying the downloaded files against `SHA256SUMS.txt` and confirming they came from this repository.
