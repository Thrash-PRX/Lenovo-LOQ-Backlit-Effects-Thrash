# Architecture

## Runtime flow

```text
Qt desktop UI
    │
    ├── EffectEngine worker thread
    │       ├── Timed brightness patterns
    │       ├── Windows keyboard hook (Reactive and Default Backlight)
    │       ├── PortAudio input (Music · Mic only)
    │       └── Windows Core Audio peak meter (Music · Speaker only)
    │
    └── KeyboardBacklightController
            │
            └── Hidden persistent Windows PowerShell process
                    │
                    └── Lenovo Vantage IdeaNotebookAddin .NET assemblies
                            │
                            └── Lenovo hardware driver
```

## Lenovo bridge

The installed Lenovo Vantage add-in exposes a private .NET API rather than a stable public SDK. The controller discovers the newest complete `IdeaNotebookAddin` directory, starts Windows PowerShell from its fixed System32 path, loads the contract assemblies, and obtains the `IdeaNotebookAgent` singleton through reflection.

Brightness changes mutate `KeyboardBacklightStatus`, serialize Lenovo's request object, and call the two-parameter `SetBacklight` method. Keeping the helper process alive avoids the startup cost of loading .NET and Lenovo assemblies for every frame.

The helper is created with `CREATE_NO_WINDOW`, receives only fixed brightness tokens, and merges output streams so a Lenovo error cannot block on an unread pipe. A controller monitor automatically reinitializes the bridge if it exits.

## Effect engine

Effects execute on a daemon worker thread. The controller serializes hardware writes with a lock. Stopping an effect signals an event, joins the worker, closes effect-specific audio resources, and restores full brightness.

## Audio modes

- Music · Mic uses `sounddevice.RawInputStream` with 16-bit mono input. RMS is calculated in memory.
- Music · Speaker uses `IAudioMeterInformation::GetPeakValue` on the current Windows render endpoint through `pycaw`.

Microphone energy uses adaptive floor/peak normalization. Speaker mode compares fast and slow output envelopes to identify sudden beat-like attacks, applies a short adaptive cooldown, and turns each onset into a bright/dim pulse. Core Audio exposes only the endpoint peak here, so no speaker samples are captured or stored.

## Battery saver and startup

Default Backlight uses the existing global keyboard hook to refresh its activity timestamp. The worker holds full brightness during activity, switches off after 10 seconds without a keypress, and wakes immediately on the next keydown.

The startup toggle creates or removes a per-user Windows Task Scheduler entry with `ONLOGON` and `HIGHEST` settings. No background service is installed.

## Packaging

PyInstaller creates a one-file Windows executable containing Python, Qt, the application icon, PortAudio support, and Core Audio bindings. Lenovo proprietary assemblies are intentionally discovered at runtime and are never included.
