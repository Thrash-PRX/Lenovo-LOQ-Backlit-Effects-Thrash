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

- Rebuilt Breathe with a stable 96 Hz scheduler, symmetric perceptual curve, protected speed range, and dropped-frame recovery instead of step-like delays
- Redesigned Wave as a clearly different fast crest, long tail, secondary ripple, and dark reset
- Rebuilt Reactive as a continuous state machine with true timed-pulse and hold-until-last-key-release behavior
- Tracked physical scan-code identities so auto-repeat and simultaneous keys cannot cause false releases
- Applied Reactive Lab choices and intensity changes live without an off/on cycle
- Reworked the header into responsive identity and status rows so the full title remains visible at 1040 px
- Added cached background blur, specular rims, rounded refraction clipping, native Windows backdrop requests, and lighter glass tinting
- Made all lighting-page descriptions and God Mode choices responsive at the minimum window size
- Made every effect card start and switch modes immediately with one click
- Renamed the product to Thrash Lightening Control
- Streamlined normal Reactive behavior to dim idle, brighten on input, fade on release, and stay active while held
- Improved speaker-output beat tracking while keeping microphone and speaker paths separate
- Renamed Default Backlight to Battery Saver and preserved the selected intensity on wake
- Hid all speed and alternate reactive options unless God Mode is enabled
- Corrected Lenovo lighting shortcut guidance to Fn+Space; Fn+Q remains the thermal-mode shortcut
- Updated application, executable, and installer metadata to 3.1.1

### Fixed

- Prevented high God Mode speeds from turning Breathe, Wave, or Reactive into flashing
- Prevented a keypress during Reactive release from waiting behind a blocking fade
- Hardened Windows keyboard-hook startup, shutdown, failure cleanup, and rapid effect switching
- Elided long bridge/status text without losing its full tooltip value

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
