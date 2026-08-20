# Contributing

Thanks for helping improve Lenovo LOQ Backlit Effects - Thrash.

## Before opening an issue

1. Install current Windows updates and Lenovo Vantage updates.
2. Confirm Lenovo Vantage can control the keyboard backlight normally.
3. Search existing issues for the laptop model and symptom.
4. Run `diagnose_vantage.py` from an administrator terminal if controller detection fails.
5. Remove usernames, serial numbers, and other personal information before attaching diagnostics.

## Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements-build.txt
py app.py
```

The application requests administrator access when started. Avoid testing high-speed strobe effects for long periods.

## Pull requests

- Keep changes focused and explain why they are needed.
- Preserve the localhost-free desktop architecture.
- Do not bundle Lenovo DLLs or other proprietary binaries.
- Do not commit signing certificates containing private keys.
- Add a concise entry to `CHANGELOG.md` for user-visible changes.
- Confirm `python -m py_compile app.py diagnose_vantage.py` passes.
- Build the PyInstaller spec when changing imports, assets, or packaging.

Compatibility pull requests should include the exact laptop model identifier and the discovered Lenovo Vantage add-in path.
