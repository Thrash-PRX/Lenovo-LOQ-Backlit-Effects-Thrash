# Changelog

All notable user-facing changes are documented here.

## [2.1.0] - 2026-08-21

### Added

- Default Backlight mode with automatic 10-second idle sleep and keypress wake
- Run at Windows Startup toggle backed by an elevated per-user scheduled task
- Adaptive speaker beat detection with transient onset tracking and beat cooldown

### Changed

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
