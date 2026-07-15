# AudioFerry v1.0.0-beta.1

Beta release candidate for Windows.

This release adopts the neutral AudioFerry product name while retaining compatibility references to AirPlay and HomePod where technically necessary.

## Changes

- Turkish and English user interface with automatic system-language default and an in-app language selector.
- Simplified Connect, Disconnect, and Find Receivers controls.
- Added four latency modes: Instant, Responsive, Balanced, and Stable.
- Instant restores the hardware-tested `latency=1 frame` and `buffer=50 ms` behavior; the remaining modes provide progressively safer fallbacks.
- Start-with-Windows registry entries now verify the exact command and correctly support both packaged and source runs.
- Selecting an output or mode no longer starts a stopped stream unexpectedly.
- Runtime and error logs rotate at 2 MB with three retained backups.
- Windows audio capture falls back to common device-native sample rates (including 48 kHz) and resamples to the AirPlay stream format when needed.
- Unsupported audio-device formats now produce one actionable failure instead of an endless reconnect and log-spam loop.
- Raw RAOP latency can be adjusted directly in the control panel down to one frame.

## Verification status

Static checks, eight offline tests, packaged startup, configuration migration, and the x64 PyInstaller build are verified. Real audible playback, clean-network discovery, reconnect after a physical network interruption, and multiple receiver/software versions still require hardware acceptance testing.

The executable is unsigned and can trigger Microsoft Defender SmartScreen. Verify the release ZIP against `SHA256SUMS.txt` before running it.
