# Changelog

All notable changes follow Keep a Changelog and Semantic Versioning.

## [1.0.0-beta.1] - 2026-07-16

### Added

- Turkish/English UI selection with system-language default.
- Exact current-user Windows startup command validation.

### Changed

- Renamed the product from HomePodBridge to AudioFerry, including executable metadata, runtime identifiers, documentation, and release artifacts.
- Simplified connection controls and added four modes: Instant, Responsive, Balanced, and Stable.
- Instant mode restores the hardware-tested one-frame RAOP latency with a 50 ms capture buffer; the other modes provide progressively safer fallbacks.
- Default gain is 1x and the default capture buffer is 50 ms.
- Raw RAOP latency is visible and adjustable down to one frame in the control panel.

### Fixed

- Selecting a device, preset, or defaults no longer starts a stopped stream unexpectedly.
- Source-mode Windows startup now invokes Python with the script path instead of relying on file association.
- Runtime and error logs rotate at 2 MB with three backups instead of growing without limit.
- WASAPI loopback capture now falls back to common Windows mix formats and resamples them to AirPlay's 44.1 kHz stream format.
- A persistent audio-device format error now stops after one diagnostic instead of reconnecting indefinitely and flooding the error log.

## [0.1.0] - 2026-07-16

### Added

- Validated configuration loading and safe fallback behavior.
- Discovered AirPlay device list, visible application version, offline tests, verification and release scripts.
- Bilingual documentation, privacy/security guidance, contribution guide, MIT license, and third-party notices.

### Changed

- Connection status now becomes “Running” only after the RAOP audio source is ready.
- Shutdown waits for audio/network cleanup.
- Runtime dependencies are complete and pinned for reproducible v0.1.0 builds.

### Security

- Removed local IP address, audio-device names, and historical logs from publishable source files.
- Added ignore rules for runtime configuration, logs, caches, and build/release output.
