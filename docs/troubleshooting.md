# Troubleshooting

## Lenovo bridge is unavailable

1. Open Lenovo Vantage and verify its keyboard backlight control works.
2. Update Lenovo Vantage and Lenovo System Interface Foundation.
3. Restart Windows after Vantage updates.
4. Start this application as administrator.
5. Select **Re-detect**.
6. Run `diagnose_vantage.py` as administrator and inspect `vantage_diagnose_report.txt`.

The expected assembly layout is similar to:

```text
C:\ProgramData\Lenovo\Vantage\Addins\IdeaNotebookAddin\<version>\
```

The directory must contain `KeyboardContract.dll`, `IdeaNotebookAddin.dll`, and `Newtonsoft.Json.dll`.

## PowerShell appears in Task Manager

This is expected. It is a hidden, non-interactive bridge to Lenovo Vantage's .NET interface. There should be no visible terminal window. If the process is closed, the application attempts to restore it automatically.

## Music · Mic does not move

- Confirm Windows allows desktop applications to access the microphone.
- Confirm the intended microphone is the Windows default input.
- Increase sensitivity.
- Close applications that hold the microphone exclusively.

## Music · Speaker does not move

- Play audio through the current Windows default output device.
- Re-select the mode after switching headphones or speakers.
- Increase sensitivity.
- Exclusive-mode playback can bypass Windows' software endpoint meter on some hardware.

## Effects stop unexpectedly

The app displays the last effect error. Re-detect the Lenovo bridge and retry at a lower speed. Very high-frequency commands may be rejected by some firmware or Vantage versions.

## Unsupported model

Compatibility is based on the Lenovo Vantage add-in contract rather than the marketing name. Open a compatibility issue with:

- Full laptop model identifier
- Windows build
- Lenovo Vantage version
- BIOS version
- Redacted diagnostic report

Do not publish serial numbers or account information.
