# Changelog

All notable user-facing changes are documented here.

## [3.1.1] - 2026-08-22

### Added

- Original five-section liquid-glass interface inspired by modern Lenovo gaming utilities
- God Mode unlock animation and progressively disclosed speed, Reactive, and Battery Saver controls
- Perceived 1–100 intensity control using 60 Hz pulse-density blending over native keyboard levels
- Battery Saver soft wake, 30-second idle sleep, and dark-at-startup behavior
- Capability-first support for additional Lenovo LOQ white-backlit models
- Device diagnostics, privacy, compatibility, credits, and expanded settings pages
- Generated Thrash liquid-glass background artwork
- Animated Thrash wordmark, Light/Dark appearance modes, and four accent themes
- Persistent top-right master power control

### Changed

- Rebuilt Breathe with a stable 96 Hz scheduler and slower soft-shouldered curve instead of step-like delays
- Made every effect card start and switch modes immediately with one click
- Renamed the product to Thrash Lightening Control
- Streamlined normal Reactive behavior to dim idle, brighten on input, fade on release, and stay active while held
- Improved speaker-output beat tracking while keeping microphone and speaker paths separate
- Renamed Default Backlight to Battery Saver and preserved the selected intensity on wake
- Hid all speed and alternate reactive options unless God Mode is enabled
- Corrected Lenovo lighting shortcut guidance to Fn+Space; Fn+Q remains the thermal-mode shortcut
- Updated application, executable, and installer metadata to 3.1.1

### Removed

- Blink, Strobe, SOS, Lightning, and Candle from the available mode catalog

## [2.1.1] - 2026-08-21

### Added

- Persistent system-tray operation with Open and Quit controls
- Task Manager-visible Startup apps registration with a tray-only boot launch
- Default Backlight mode with automatic 10-second idle sleep and keypress wake
- Run at Windows Startup toggle backed by an elevated per-user scheduled task
- Adaptive speaker beat detection with transient onset tracking and beat cooldown
- Single LZMA2-compressed Windows installer containing the app and verification files

### Changed

- Fixed the completion-page launch failing with Windows error 740 when the app requires administrator rights
- Reworked typography, capitalization, effect cards, header, and Thrash brand mark
- Replaced mixed emoji artwork with a consistent monochrome symbol system
- Renamed React to Reactive and clarified both music-mode labels
- Updated audio and battery-state status messages

## [2.0.0] - 2026-08-21

### Added

- Native Qt desktop interface with no localhost server
- Animated LOQ-inspired startup sequence
- Procedural ambient background and custom application icon
- Wave lighting effect
- Separate Music · Mic and Music · Speaker modes
- Live music level meter and sensitivity control
- Self-recovering hidden Lenovo Vantage bridge
- Thrash product metadata and Authenticode signing support

### Changed

- Replaced the original browser UI with modern effect cards
- Improved Lenovo DLL discovery and command validation
- Improved keyboard hook shutdown behavior
- Corrected source-mode administrator relaunching

### Removed

- Flask runtime and HTML templates
- Caps/Num/Scroll Lock fallback that changed keyboard lock states
