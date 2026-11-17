# AudioFerry v1.0.0-beta.3

Reliability update for long-running Windows-to-AirPlay streams. v1.0.0-beta.2 only changed the license and still used the v1.0.0-beta.1 audio code, so it dropped out more often; this release brings the reliability fixes back.

## Changes

- The configured capture buffer is filled before transmission begins.
- Continuous adaptive clock-drift compensation keeps the Windows capture and AirPlay sender queues synchronized.
- Partial audio packets are preserved while the buffer recovers instead of causing a multi-second silence cascade.
- WASAPI capture automatically reopens when Windows invalidates or reconfigures the selected output device.
- Device teardown failures are handled safely during recovery and shutdown.
- The selected Windows output is used exclusively; AudioFerry no longer reports success while silently capturing another device.
- Stronger single-instance locking prevents two packaged copies from competing for the same Windows audio output.

AudioFerry is licensed under the PolyForm Noncommercial License 1.0.0: personal and other noncommercial use only. See `LICENSE`.

## Verification status

Static checks, the offline test suite, packaged startup and the x64 PyInstaller build are verified. Extended audible playback on the target AirPlay receiver remains the final hardware acceptance test.

The executable is unsigned and can trigger Microsoft Defender SmartScreen. Verify the release ZIP against `SHA256SUMS.txt` before running it.
