# Architecture and Network Behavior

AudioFerry is a single-process Python desktop application:

1. Tkinter provides the settings/status panel; `pystray` provides the notification-area menu.
2. SoundCard opens the selected Windows WASAPI loopback device and a worker thread converts floating-point samples to big-endian 16-bit PCM with NumPy.
3. `pyatv` and `zeroconf` discover `_raop._tcp`/AirPlay services through mDNS and create the RAOP stream. Protocol latency is left at the receiver/`pyatv` negotiated default; the application does not advertise or force unrealistic millisecond latency.
4. The asyncio streaming worker sends PCM to the selected receiver and retries after errors until stopped.
5. Shutdown signals the stream, closes the recorder, tears down RAOP playback, closes the connection, and waits for the worker.

No server is started and no inbound listening port is intentionally exposed by application code. Discovery uses multicast UDP 5353. The receiver advertises its AirPlay/RAOP service port; subsequent RTP control, timing, and audio ports are negotiated and therefore cannot be represented by one fixed port list. All audio traffic is intended for the selected LAN receiver. There is no telemetry or Internet update path.

## Experimental boundary

The stream implementation accesses private `pyatv` objects (`_interfaces`, playback manager, and RAOP context) to inject live system PCM and latency settings. This is functional code, not a stable public API contract. The `pyatv` version is pinned and upgrades require an end-to-end hardware test.
