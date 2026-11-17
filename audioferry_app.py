from __future__ import annotations

import argparse
import asyncio
import ctypes
import ipaddress
import json
import locale
import os
import signal
import sys
import threading
import time
import tkinter as tk
import traceback
import winreg
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

import numpy as np
import pystray
import soundcard as sc
from PIL import Image, ImageDraw
from pyatv import connect, scan
from pyatv.const import Protocol
from pyatv.interface import Audio, Metadata, PushUpdater, RemoteControl
from pyatv.protocols.airplay.auth import extract_credentials
from pyatv.protocols.raop.audio_source import AudioSource
from pyatv.support.metadata import MediaMetadata

APP_NAME = "AudioFerry"
APP_VERSION = "1.0.0-beta.1"
CURRENT_LANGUAGE = "tr" if (locale.getlocale()[0] or "").lower().startswith("tr") else "en"
DEFAULT_CONFIG = {
    "address": "",
    "auto_detect": True,
    "device": None,
    "volume": 60,
    "gain": 1,
    "buffer_ms": 50,
    "latency_frames": 1,
    "language": CURRENT_LANGUAGE,
    "install_done": False,
    "setup_done": False,
}
PRESETS = {
    "instant": {"buffer_ms": 50, "latency_frames": 1},
    "responsive": {"buffer_ms": 75, "latency_frames": 4410},
    "balanced": {"buffer_ms": 150, "latency_frames": 11025},
    "stable": {"buffer_ms": 500, "latency_frames": 66150},
}
STATUS_TEXT = {
    "Starting": "Başlıyor",
    "Running": "Çalışıyor",
    "Reconnect": "Tekrar bağlanıyor",
    "Stopped": "Durdu",
}

UI_EN = {
    "Başlıyor": "Starting",
    "Çalışıyor": "Connected",
    "Tekrar bağlanıyor": "Reconnecting",
    "Durdu": "Stopped",
    "Hazır": "Ready",
    "Durum": "Status",
    "Bağlan": "Connect",
    "Bağlantıyı Kes": "Disconnect",
    "Mod": "Mode",
    "Anlık": "Instant",
    "Tepkisel": "Responsive",
    "Dengeli": "Balanced",
    "Stabil": "Stable",
    "Kontrol Paneli": "Control Panel",
    "Ayar Dosyasını Aç": "Open Settings File",
    "Log Aç": "Open Log",
    "Hata Logu Aç": "Open Error Log",
    "Uygulamadan Çık": "Exit",
    "İlk kurulum: alıcıyı bul, ses çıkışını seç ve bağlan.": "First setup: find a receiver, select an audio output, and connect.",
    "Windows sesini yerel ağdaki uyumlu bir alıcıya aktar.": "Stream Windows audio to a compatible receiver on your local network.",
    "Kontrol": "Control",
    "Ayrıntılar": "Details",
    "İlk Kurulum": "First Setup",
    "1. AirPlay alıcılarını bul": "1. Find AirPlay receivers",
    "2. Yakalanacak ses çıkışını seç": "2. Select the audio output to capture",
    "3. Bağlan düğmesine bas": "3. Click Connect",
    "Bulunan alıcılar": "Discovered receivers",
    "IP adresi": "IP address",
    "Adres çalışmazsa otomatik bul": "Discover automatically if the address fails",
    "Ses": "Audio",
    "Çıkış": "Output",
    "Windows ses karıştırıcısında uygulamanın bu çıkışı kullandığından emin ol.": "Make sure the source app uses this output in Windows Volume Mixer.",
    "Ses seviyesi": "Volume",
    "Ses güçlendirme": "Audio boost",
    "Akış Dayanıklılığı": "Stream Resilience",
    "Yakalama tamponu": "Capture buffer",
    "RAOP gecikmesi": "RAOP latency",
    "Anlık mod 1 karelik deneysel gecikmeyi kullanır. Sorun olursa diğer modlardan birini seç.": "Instant mode uses an experimental one-frame latency. Select another mode if it causes problems.",
    "Kontroller": "Controls",
    "Modlar": "Modes",
    "Dosyalar": "Files",
    "Son Log": "Recent Log",
    "Alıcıları Bul": "Find Receivers",
    "Windows ile başlat": "Start with Windows",
    "Dil": "Language",
    "Varsayılanlara Dön": "Restore Defaults",
    "Logu Aç": "Open Log",
    "Henüz log yok.": "No log entries yet.",
    "İlk kurulum gerekli": "First setup required",
    "Yerel ağda uyumlu bir AirPlay alıcısı bulunamadı.": "No compatible AirPlay receiver was found on the local network.",
    "AirPlay alıcısı bulundu.": "AirPlay receiver found.",
    "AirPlay alıcısı bulundu": "AirPlay receivers found",
    "Varsayılanlara dönüldü.": "Defaults restored.",
    "Windows ile başlatma açıldı": "Start with Windows enabled",
    "Windows ile başlatma kapatıldı": "Start with Windows disabled",
    "Alıcıya bağlanılıyor": "Connecting to receiver",
    "Seçili ses çıkışı açılamadı": "The selected audio output could not be opened",
    "AirPlay alıcısı": "AirPlay receiver",
}


def set_language(language: str) -> None:
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = language if language in {"tr", "en"} else "en"


def ui(text: str) -> str:
    return UI_EN.get(text, text) if CURRENT_LANGUAGE == "en" else text


def tr_status(status: str) -> str:
    return ui(STATUS_TEXT.get(status, status))


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("APPDATA", Path.home())) / "AudioFerry"
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
CONFIG_PATH = BASE_DIR / "bridge_config.json"
LOG_PATH = BASE_DIR / "bridge.log"
ERR_PATH = BASE_DIR / "bridge.err.log"
LOCK_PATH = BASE_DIR / "audioferry.lock"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AudioFerry"
STARTUP_PATH = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
    / "AudioFerry.cmd"
)
MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3
LOG_LOCK = threading.Lock()


def rotate_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    if path.stat().st_size > MAX_LOG_BYTES * 2:
        path.unlink()
        return
    oldest = path.with_name(f"{path.name}.{LOG_BACKUPS}")
    if oldest.exists():
        oldest.unlink()
    for index in range(LOG_BACKUPS - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def log(message: str, error: bool = False) -> None:
    path = ERR_PATH if error else LOG_PATH
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK:
        rotate_log(path)
        with path.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")


def validate_config(config: object) -> dict:
    """Return a safe, normalized configuration without trusting user JSON."""
    if not isinstance(config, dict):
        return dict(DEFAULT_CONFIG)

    normalized = dict(DEFAULT_CONFIG)
    address = str(config.get("address") or "").strip()
    if address:
        try:
            ipaddress.ip_address(address)
        except ValueError:
            address = ""
    normalized["address"] = address
    normalized["auto_detect"] = bool(config.get("auto_detect", True))
    device = config.get("device")
    normalized["device"] = str(device).strip() if device else None
    language = str(config.get("language") or DEFAULT_CONFIG["language"]).lower()
    normalized["language"] = language if language in {"tr", "en"} else DEFAULT_CONFIG["language"]

    limits = {
        "volume": (0, 100),
        "gain": (1, 2),
        "buffer_ms": (50, 750),
        "latency_frames": (1, 66150),
    }
    for key, (minimum, maximum) in limits.items():
        try:
            value = int(float(config.get(key, DEFAULT_CONFIG[key])))
        except (TypeError, ValueError):
            value = int(str(DEFAULT_CONFIG[key]))
        normalized[key] = max(minimum, min(maximum, value))

    normalized["install_done"] = bool(config.get("install_done", False))
    normalized["setup_done"] = bool(config.get("setup_done", False))
    return normalized


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
                loaded = json.load(file)
            config = validate_config(loaded)
        except (json.JSONDecodeError, OSError) as ex:
            backup_path = CONFIG_PATH.with_suffix(".bad.json")
            try:
                CONFIG_PATH.replace(backup_path)
            except OSError:
                pass
            log(f"Config okunamadı, varsayılan ayarlar kullanıldı: {ex}", error=True)
            save_config(config)
    else:
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def save_config(config: dict) -> None:
    merged = validate_config(config)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def startup_task_installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
        return str(value).strip().casefold() == startup_command().casefold()
    except FileNotFoundError:
        return False


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" --minimized'
    return f'"{Path(sys.executable).resolve()}" "{Path(__file__).resolve()}" --minimized'


def set_startup_task(enabled: bool) -> None:
    if STARTUP_PATH.exists():
        STARTUP_PATH.unlink()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def list_audio_devices() -> str:
    lines = [f"Default speaker: {sc.default_speaker().name}", "", "Speakers:"]
    lines.extend(f" - {speaker.name}" for speaker in sc.all_speakers())
    lines.extend(["", "Capture/loopback devices:"])
    lines.extend(f" - {microphone.name}" for microphone in sc.all_microphones(include_loopback=True))
    return "\n".join(lines)


async def discover_airplay_devices(timeout: int = 5):
    configs = await scan(asyncio.get_running_loop(), timeout=timeout)
    return [
        config
        for config in configs
        if config.get_service(Protocol.RAOP) is not None or config.get_service(Protocol.AirPlay) is not None
    ]


async def discover_receiver(timeout: int = 5):
    candidates = await discover_airplay_devices(timeout)
    if not candidates:
        return None
    return candidates[0]


async def resolve_receiver_config(config: dict):
    address = str(config.get("address") or "").strip()
    if address:
        configs = await scan(asyncio.get_running_loop(), hosts=[address], timeout=4)
        if configs:
            return configs[0]
        if not config.get("auto_detect", True):
            raise RuntimeError(f"No Apple/AirPlay device found at {address}")

    device_config = await discover_receiver(timeout=6)
    if device_config is None:
        raise RuntimeError("No compatible AirPlay receiver found on the network")

    if device_config.address:
        config["address"] = str(device_config.address)
        save_config(config)
    return device_config


def pick_loopback(device_name: Optional[str]):
    microphones = sc.all_microphones(include_loopback=True)
    if device_name:
        lowered = device_name.lower()
        for microphone in microphones:
            if lowered in microphone.name.lower():
                return microphone
        names = "\n".join(f" - {microphone.name}" for microphone in microphones)
        raise RuntimeError(f"No loopback device matched {device_name!r}.\nAvailable devices:\n{names}")

    default_name = sc.default_speaker().name
    for microphone in microphones:
        if microphone.name == default_name:
            return microphone

    for microphone in microphones:
        if default_name.lower() in microphone.name.lower():
            return microphone

    names = "\n".join(f" - {microphone.name}" for microphone in microphones)
    raise RuntimeError(f"Could not find loopback for default speaker {default_name!r}.\nAvailable devices:\n{names}")


def output_device_names() -> list[str]:
    blocked = ("microphone", "mikrofon", "quadcast")
    names = []
    for speaker in sc.all_speakers():
        name = speaker.name
        if any(part in name.lower() for part in blocked):
            continue
        names.append(name)
    if not names:
        names.append(sc.default_speaker().name)
    return names


def normalize_output_device(device_name: Optional[str]) -> Optional[str]:
    if not device_name:
        return None

    outputs = output_device_names()
    if device_name in outputs:
        return device_name

    lowered = device_name.lower()
    for output in outputs:
        output_lowered = output.lower()
        if lowered in output_lowered or output_lowered in lowered:
            log(f"Ses çıkışı eşleştirildi: {device_name} -> {output}")
            return output

    log(f"Ses çıkışı bu bilgisayarda yok, varsayılan çıkış kullanılacak: {device_name}", error=True)
    return None


def loopback_candidates(device_name: Optional[str]):
    microphones = sc.all_microphones(include_loopback=True)
    names = []
    normalized_device = normalize_output_device(device_name)
    if normalized_device:
        names.append(normalized_device)
    names.append(sc.default_speaker().name)
    names.extend(output_device_names())

    seen = set()
    candidates = []
    for name in names:
        lowered = (name or "").lower()
        for microphone in microphones:
            mic_name = microphone.name.lower()
            if (lowered and (lowered == mic_name or lowered in mic_name or mic_name in lowered)) and microphone.name not in seen:
                seen.add(microphone.name)
                candidates.append(microphone)
    return candidates


class AudioCaptureError(RuntimeError):
    """Raised when Windows cannot open any compatible loopback format."""


def capture_format_candidates(microphone, output_rate: int, output_channels: int) -> list[tuple[int, int]]:
    """Return likely WASAPI formats, preferring the device channel layout."""
    try:
        device_channels = max(1, int(microphone.channels))
    except Exception:
        device_channels = output_channels

    formats = []
    for rate in (output_rate, 48000, 44100, 96000):
        for channel_count in (device_channels, output_channels, 2, 1):
            candidate = (int(rate), min(max(1, int(channel_count)), device_channels))
            if candidate not in formats:
                formats.append(candidate)
    return formats


class LinearAudioResampler:
    """Small stateful linear resampler for WASAPI-to-RAOP conversion."""

    def __init__(self, input_rate: int, output_rate: int) -> None:
        self.input_rate = input_rate
        self.output_rate = output_rate
        self._position = 0.0
        self._tail: Optional[np.ndarray] = None

    def process(self, data: np.ndarray) -> np.ndarray:
        if self.input_rate == self.output_rate or len(data) == 0:
            return data
        if data.ndim == 1:
            data = data.reshape((-1, 1))

        samples = data if self._tail is None else np.concatenate((self._tail, data), axis=0)
        if len(samples) < 2:
            self._tail = samples[-1:].copy()
            return np.empty((0, samples.shape[1]), dtype=samples.dtype)

        step = self.input_rate / self.output_rate
        positions = np.arange(self._position, len(samples) - 1, step, dtype=np.float64)
        if len(positions) == 0:
            self._position -= len(samples) - 1
            self._tail = samples[-1:].copy()
            return np.empty((0, samples.shape[1]), dtype=samples.dtype)

        lower = positions.astype(np.int64)
        fraction = (positions - lower).reshape((-1, 1))
        output = samples[lower] * (1.0 - fraction) + samples[lower + 1] * fraction
        self._position = float(positions[-1] + step - (len(samples) - 1))
        self._tail = samples[-1:].copy()
        return output.astype(data.dtype, copy=False)


def normalize_raop_latency_frames(latency_frames: int) -> int:
    """Bound the raw RAOP latency while retaining the proven one-frame mode."""
    return max(1, min(66150, int(latency_frames)))


class LoopbackAudioSource(AudioSource):
    def __init__(
        self,
        device_name: Optional[str],
        sample_rate: int,
        channels: int,
        sample_size: int,
        gain: float,
        buffer_ms: int,
    ) -> None:
        if sample_size != 2:
            raise RuntimeError(f"Only 16-bit AirPlay samples are supported, got {sample_size} bytes")

        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_size = sample_size
        self._gain = gain
        self._gain_lock = threading.Lock()
        self._frame_size = channels * sample_size
        self._buffer_target_bytes = max(
            int(sample_rate * (buffer_ms / 1000.0) * self._frame_size),
            self._frame_size * 1024,
        )
        self._audio_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        self._closed = False
        self._last_underrun_log = 0.0
        self._last_capture_log = 0.0
        self._loop = asyncio.get_running_loop()

        self._microphone = None
        self._recorder = None
        self._capture_sample_rate = sample_rate
        self._capture_channels = channels
        self._resampler = LinearAudioResampler(sample_rate, sample_rate)
        self._open_recorder(device_name)
        self._capture_thread = threading.Thread(target=self._capture_worker, name="loopback-capture", daemon=True)
        self._capture_thread.start()

    def _open_recorder(self, device_name: Optional[str]) -> None:
        errors = []
        candidates = loopback_candidates(device_name)
        if not candidates:
            candidates = [pick_loopback(device_name)]

        for microphone in candidates:
            for capture_rate, capture_channels in capture_format_candidates(
                microphone, self._sample_rate, self._channels
            ):
                for blocksize in (None, 256, 512, 1024):
                    try:
                        kwargs = {"samplerate": capture_rate, "channels": capture_channels}
                        if blocksize is not None:
                            kwargs["blocksize"] = blocksize
                        recorder = microphone.recorder(**kwargs)
                        recorder.__enter__()
                        self._microphone = microphone
                        self._recorder = recorder
                        self._capture_sample_rate = capture_rate
                        self._capture_channels = capture_channels
                        self._resampler = LinearAudioResampler(capture_rate, self._sample_rate)
                        log(
                            f"Audio output captured: {microphone.name}, "
                            f"capture={capture_rate}Hz/{capture_channels}ch, "
                            f"airplay={self._sample_rate}Hz/{self._channels}ch"
                        )
                        return
                    except Exception as ex:
                        errors.append(
                            f"{microphone.name} rate={capture_rate} channels={capture_channels} "
                            f"block={blocksize}: {ex}"
                        )

        raise AudioCaptureError("Ses çıkışı açılamadı:\n" + "\n".join(errors[-12:]))

    def _capture_worker(self) -> None:
        if self._recorder is None:
            return
        while not self._closed:
            try:
                data = self._recorder.record(numframes=1024)
                pcm = self._float_to_airplay_pcm(data)
            except Exception as ex:
                now = time.monotonic()
                if now - self._last_capture_log > 5:
                    self._last_capture_log = now
                    log(f"Ses yakalama durakladi, sessizlik dolduruluyor: {ex}", error=True)
                silence_frames = round(1024 * self._sample_rate / self._capture_sample_rate)
                pcm = self._silence_frames(silence_frames)
                time.sleep(0.02)
            with self._buffer_lock:
                self._audio_buffer.extend(pcm)
                max_bytes = max(self._buffer_target_bytes * 2, self._frame_size * 4096)
                if len(self._audio_buffer) > max_bytes:
                    del self._audio_buffer[: len(self._audio_buffer) - max_bytes]

    async def close(self) -> None:
        self._closed = True
        await self._loop.run_in_executor(None, self._capture_thread.join, 1.0)
        if self._recorder is not None:
            self._recorder.__exit__(None, None, None)

    def _float_to_airplay_pcm(self, data: np.ndarray) -> bytes:
        if data.ndim == 1:
            data = data.reshape((-1, 1))

        data = self._resampler.process(data)

        if data.shape[1] < self._channels:
            data = np.repeat(data, self._channels, axis=1)
        elif data.shape[1] > self._channels:
            data = data[:, : self._channels]

        with self._gain_lock:
            gain = self._gain
        data = np.clip(data * gain, -1.0, 1.0)
        pcm = (data * 32767.0).astype("<i2", copy=False)
        return pcm.byteswap().tobytes()

    def set_gain(self, gain: float) -> None:
        with self._gain_lock:
            self._gain = gain

    def _silence_frames(self, nframes: int) -> bytes:
        return b"\x00" * (nframes * self._frame_size)

    def _log_underrun(self) -> None:
        now = time.monotonic()
        if now - self._last_underrun_log > 5:
            self._last_underrun_log = now
            log("Buffer bosaldi, akisi korumak icin sessizlik dolduruldu")

    async def readframes(self, nframes: int) -> bytes:
        if self._closed:
            return AudioSource.NO_FRAMES

        bytes_needed = nframes * self._frame_size
        with self._buffer_lock:
            available_len = len(self._audio_buffer)
            if available_len >= bytes_needed:
                data = bytes(self._audio_buffer[:bytes_needed])
                del self._audio_buffer[:bytes_needed]
                return data

            if available_len > 0:
                available = bytes(self._audio_buffer[:available_len])
                self._audio_buffer.clear()
                missing = bytes_needed - len(available)
                self._log_underrun()
                return available + (b"\x00" * max(0, missing))

        self._log_underrun()
        return self._silence_frames(nframes)

    async def get_metadata(self) -> MediaMetadata:
        return MediaMetadata(title="Windows Audio", artist="AudioFerry")

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def sample_size(self) -> int:
        return self._sample_size

    @property
    def duration(self) -> int:
        return 0


async def stream_once(config: dict, stop_event: threading.Event, runner=None) -> None:
    config = dict(config)
    config["device"] = normalize_output_device(config.get("device"))
    device_config = await resolve_receiver_config(config)
    atv = await connect(device_config, asyncio.get_running_loop(), protocol=Protocol.RAOP)
    source: Optional[LoopbackAudioSource] = None
    takeover_release = None

    try:
        stream = atv.stream._interfaces[Protocol.RAOP]  # type: ignore[attr-defined]
        stream.playback_manager.acquire()
        takeover_release = stream.core.takeover(Audio, Metadata, PushUpdater, RemoteControl)

        client, context = await stream.playback_manager.setup(stream.core.service)
        context.credentials = extract_credentials(stream.core.service)
        context.password = stream.core.service.password
        client.listener = stream.listener
        await client.initialize(stream.core.service.properties)
        source = LoopbackAudioSource(
            device_name=config["device"],
            sample_rate=context.sample_rate,
            channels=context.channels,
            sample_size=context.bytes_per_channel,
            gain=config["gain"],
            buffer_ms=config["buffer_ms"],
        )
        if runner is not None:
            runner.attach_live_controls(asyncio.get_running_loop(), stream.audio, source)
            runner.mark_running(device_config.name)
        send_task = asyncio.create_task(client.send_audio(source, await source.get_metadata(), volume=config["volume"]))
        # send_audio resets the context before its first await. Yield once, then apply
        # the receiver-advertised latency range before audio packets are emitted.
        await asyncio.sleep(0)
        context.latency = normalize_raop_latency_frames(config["latency_frames"])
        log(
            f"Streaming {getattr(source._microphone, 'name', 'Windows loopback')} -> {device_config.name} "
            f"({config['address']}), capture_buffer={config['buffer_ms']}ms, "
            f"raop_latency={context.latency}frames"
        )
        while not stop_event.is_set() and not send_task.done():
            await asyncio.sleep(0.25)
        if not send_task.done():
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
        else:
            await send_task
    finally:
        if runner is not None:
            runner.detach_live_controls(source)
        if source is not None:
            await source.close()
        if takeover_release is not None:
            takeover_release()
        try:
            await atv.stream._interfaces[Protocol.RAOP].playback_manager.teardown()  # type: ignore[attr-defined]
        finally:
            atv.close()


class BridgeRunner:
    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.running = False
        self.status = "Stopped"
        self.detail = ""
        self.last_error = ""
        self.loop = None
        self.current_audio = None
        self.current_source = None
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._worker, name="audioferry-bridge", daemon=True)
            self.thread.start()
            self.running = True
            self.status = "Starting"
            self.detail = ui("Alıcıya bağlanılıyor")

    def stop(self) -> None:
        with self.lock:
            self.stop_event.set()
            self.running = False
            self.status = "Stopped"
            self.detail = ""

    def shutdown(self, timeout: float = 10.0) -> bool:
        """Request shutdown and wait for audio/network resources to be released."""
        thread = self.thread
        self.stop()
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        return not (thread and thread.is_alive())

    def mark_running(self, device_name: str) -> None:
        self.status = "Running"
        self.detail = f"AirPlay: {device_name}"
        self.last_error = ""

    def restart(self) -> None:
        old_thread = self.thread
        self.stop()
        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=8)
            if old_thread.is_alive():
                log("Yeniden başlatma ertelendi: eski ses akışı hâlâ kapanıyor", error=True)
                with self.lock:
                    self.thread = old_thread
                    self.running = True
                    self.status = "Reconnect"
                    self.detail = "Eski akış kapanıyor"
                return
        with self.lock:
            self.thread = None
            self.running = False
        self.start()

    def attach_live_controls(self, loop, audio, source) -> None:
        with self.lock:
            self.loop = loop
            self.current_audio = audio
            self.current_source = source

    def detach_live_controls(self, source) -> None:
        with self.lock:
            if self.current_source is source:
                self.current_source = None
                self.current_audio = None
                self.loop = None

    def apply_live_volume(self, volume: int) -> None:
        with self.lock:
            loop = self.loop
            audio = self.current_audio
        if loop is None or audio is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(audio.set_volume(float(volume)), loop)
        except RuntimeError as ex:
            log(f"Live volume failed: {ex}", error=True)

    def apply_live_gain(self, gain: int) -> None:
        with self.lock:
            source = self.current_source
        if source is not None:
            source.set_gain(float(gain))

    def _worker(self) -> None:
        while not self.stop_event.is_set():
            config = load_config()
            try:
                self.status = "Starting"
                self.detail = ui("Alıcıya bağlanılıyor")
                asyncio.run(stream_once(config, self.stop_event, self))
            except AudioCaptureError as ex:
                self.last_error = str(ex)
                self.detail = ui("Seçili ses çıkışı açılamadı")
                log(f"Audio capture error: {ex}", error=True)
                self.stop_event.set()
                break
            except Exception as ex:
                self.status = "Reconnect"
                self.last_error = str(ex)
                self.detail = self.last_error[:80]
                log(f"Bridge error: {ex}\n{traceback.format_exc()}", error=True)
                for _ in range(10):
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.5)
            else:
                if not self.stop_event.is_set():
                    time.sleep(2)
        self.running = False
        self.status = "Stopped"


class TrayApp:
    def __init__(self) -> None:
        set_language(str(load_config().get("language", DEFAULT_CONFIG["language"])))
        self.runner = BridgeRunner()
        self.exit_event = threading.Event()
        self.icon = pystray.Icon("audioferry", self._make_icon((60, 150, 255)), APP_NAME, self._menu())
        self.menu_thread = threading.Thread(target=self._refresh_menu, daemon=True)

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"{ui('Durum')}: {tr_status(self.runner.status)}", None, enabled=False),
            pystray.MenuItem(lambda _: self.runner.detail or ui("Hazır"), None, enabled=False),
            pystray.MenuItem(ui("Bağlan"), lambda _: self._start(), enabled=lambda _: not self.runner.running),
            pystray.MenuItem(ui("Bağlantıyı Kes"), lambda _: self._stop(), enabled=lambda _: self.runner.running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                ui("Mod"),
                pystray.Menu(
                    pystray.MenuItem(ui("Anlık"), lambda _: self._apply_preset("instant")),
                    pystray.MenuItem(ui("Tepkisel"), lambda _: self._apply_preset("responsive")),
                    pystray.MenuItem(ui("Dengeli"), lambda _: self._apply_preset("balanced")),
                    pystray.MenuItem(ui("Stabil"), lambda _: self._apply_preset("stable")),
                ),
            ),
            pystray.MenuItem(ui("Kontrol Paneli"), lambda _: self._open_settings()),
            pystray.MenuItem(ui("Ayar Dosyasını Aç"), lambda _: self._open_path(CONFIG_PATH)),
            pystray.MenuItem(ui("Log Aç"), lambda _: self._open_path(LOG_PATH)),
            pystray.MenuItem(ui("Hata Logu Aç"), lambda _: self._open_path(ERR_PATH)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(ui("Uygulamadan Çık"), lambda _: self._exit()),
        )

    @staticmethod
    def _make_icon(color: tuple[int, int, int]) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((10, 6, 54, 58), radius=14, fill=color)
        draw.ellipse((24, 20, 40, 36), fill=(255, 255, 255, 235))
        draw.arc((16, 12, 48, 44), 210, 330, fill=(255, 255, 255, 180), width=4)
        draw.arc((8, 4, 56, 52), 210, 330, fill=(255, 255, 255, 120), width=4)
        return image

    def _set_color(self) -> None:
        if self.runner.status == "Running":
            self.icon.icon = self._make_icon((40, 190, 110))
        elif self.runner.status == "Reconnect":
            self.icon.icon = self._make_icon((245, 170, 40))
        else:
            self.icon.icon = self._make_icon((120, 120, 120))

    def _start(self) -> None:
        self.runner.start()
        self._set_color()
        self.icon.update_menu()

    def _stop(self) -> None:
        self.runner.stop()
        self._set_color()
        self.icon.update_menu()

    def _apply_preset(self, name: str) -> None:
        config = load_config()
        config.update(PRESETS[name])
        save_config(config)
        log(f"Preset applied: {name}")
        if self.runner.running:
            self.runner.restart()
        self._set_color()
        self.icon.update_menu()

    def _exit(self) -> None:
        if not self.runner.shutdown():
            log("Uygulama kapanırken ses akışı zamanında sonlanmadı", error=True)
        self.exit_event.set()
        self.icon.stop()

    def _open_path(self, path: Path) -> None:
        path.touch(exist_ok=True)
        os.startfile(path)

    def _open_settings(self) -> None:
        threading.Thread(target=self._settings_window, name="settings-window", daemon=True).start()

    def _settings_window(self) -> None:
        config = load_config()
        first_setup = not bool(config.get("setup_done", False))
        root = tk.Tk()
        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("820x560")
        root.minsize(800, 540)
        root.configure(background="#f3f5f7")

        devices = output_device_names()
        selected_device = str(config.get("device") or "")
        if selected_device not in devices and devices:
            selected_device = devices[0]

        variables = {
            "address": tk.StringVar(value=str(config.get("address") or "")),
            "auto_detect": tk.BooleanVar(value=bool(config.get("auto_detect", True))),
            "device": tk.StringVar(value=selected_device),
            "volume": tk.IntVar(value=int(float(config.get("volume", 60)))),
            "gain": tk.IntVar(value=int(float(config.get("gain", 1)))),
            "buffer_ms": tk.IntVar(value=int(config.get("buffer_ms", 50))),
            "latency_frames": tk.IntVar(value=int(config.get("latency_frames", 1))),
            "language": tk.StringVar(value="Türkçe" if config.get("language") == "tr" else "English"),
            "startup": tk.BooleanVar(value=startup_task_installed()),
        }

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 9))
        style.configure("App.TFrame", background="#f3f5f7")
        style.configure("Header.TFrame", background="#101820")
        style.configure("HeaderTitle.TLabel", background="#101820", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("HeaderText.TLabel", background="#101820", foreground="#c7d2da", font=("Segoe UI", 9))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Section.TLabelframe", background="#f3f5f7")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"), foreground="#101820")
        style.configure("Hint.TLabel", foreground="#4b5563", font=("Segoe UI", 9))
        style.configure("Value.TLabel", foreground="#111827", font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 7))
        style.configure("Tool.TButton", padding=(8, 6))

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, style="Header.TFrame", padding=(16, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=f"{APP_NAME}  v{APP_VERSION}", style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=ui("İlk kurulum: alıcıyı bul, ses çıkışını seç ve bağlan.")
            if first_setup
            else ui("Windows sesini yerel ağdaki uyumlu bir alıcıya aktar."),
            style="HeaderText.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        status_var = tk.StringVar(value=f"{tr_status(self.runner.status)} - {self.runner.detail or ui('Hazır')}")
        ttk.Label(header, textvariable=status_var, style="HeaderText.TLabel").grid(row=0, column=1, sticky="e", padx=(16, 0))

        main = ttk.Frame(root, padding=(10, 8, 10, 10), style="App.TFrame")
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(main)
        notebook.grid(row=0, column=0, sticky="nsew")

        dashboard = ttk.Frame(notebook, padding=8, style="App.TFrame")
        advanced = ttk.Frame(notebook, padding=12, style="App.TFrame")
        notebook.add(dashboard, text=ui("Kontrol"))
        notebook.add(advanced, text=ui("Ayrıntılar"))
        dashboard.columnconfigure(0, weight=3)
        dashboard.columnconfigure(1, weight=2)
        advanced.columnconfigure(0, weight=1)
        advanced.rowconfigure(1, weight=1)

        left_col = ttk.Frame(dashboard, style="App.TFrame")
        left_col.grid(row=0, column=0, sticky="new", padx=(0, 8))
        left_col.columnconfigure(0, weight=1)
        right_col = ttk.Frame(dashboard, style="App.TFrame")
        right_col.grid(row=0, column=1, sticky="new", padx=(8, 0))
        right_col.columnconfigure(0, weight=1)

        if first_setup:
            setup = ttk.LabelFrame(left_col, text=ui("İlk Kurulum"), padding=8, style="Section.TLabelframe")
            setup.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            setup.columnconfigure(1, weight=1)
            ttk.Label(setup, text=ui("1. AirPlay alıcılarını bul")).grid(row=0, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(setup, text=ui("2. Yakalanacak ses çıkışını seç")).grid(row=1, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(setup, text=ui("3. Bağlan düğmesine bas")).grid(row=2, column=0, sticky="w", pady=2)
            row_offset = 1
        else:
            row_offset = 0

        connection = ttk.LabelFrame(left_col, text=ui("AirPlay alıcısı"), padding=8, style="Section.TLabelframe")
        connection.grid(row=0 + row_offset, column=0, sticky="ew", pady=(0, 8))
        connection.columnconfigure(1, weight=1)
        discovered_by_label: dict[str, str] = {}
        variables["target"] = tk.StringVar(value="")
        ttk.Label(connection, text=ui("Bulunan alıcılar")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        target_box = ttk.Combobox(connection, textvariable=variables["target"], state="readonly")
        target_box.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(connection, text=ui("IP adresi")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(connection, textvariable=variables["address"]).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(connection, text=ui("Adres çalışmazsa otomatik bul"), variable=variables["auto_detect"]).grid(
            row=2, column=1, sticky="w", pady=(0, 2)
        )

        audio = ttk.LabelFrame(left_col, text=ui("Ses"), padding=8, style="Section.TLabelframe")
        audio.grid(row=1 + row_offset, column=0, sticky="ew", pady=(0, 8))
        audio.columnconfigure(1, weight=1)
        ttk.Label(audio, text=ui("Çıkış")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        device_box = ttk.Combobox(audio, textvariable=variables["device"], values=devices, state="readonly")
        device_box.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(audio, text=ui("Windows ses karıştırıcısında uygulamanın bu çıkışı kullandığından emin ol.")).grid(
            row=1, column=1, columnspan=3, sticky="w", pady=(0, 3)
        )
        ttk.Label(audio, text=ui("Ses seviyesi")).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Scale(audio, from_=0, to=100, variable=variables["volume"], command=lambda value: variables["volume"].set(round(float(value)))).grid(  # type: ignore[arg-type]
            row=2, column=1, sticky="ew", pady=3
        )
        ttk.Spinbox(audio, from_=0, to=100, textvariable=variables["volume"], width=6).grid(row=2, column=2, padx=(8, 0), pady=3)
        ttk.Label(audio, text="%").grid(row=2, column=3, sticky="w", padx=(4, 0), pady=3)
        ttk.Label(audio, text=ui("Ses güçlendirme")).grid(row=3, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Scale(audio, from_=1, to=2, variable=variables["gain"], command=lambda value: variables["gain"].set(round(float(value)))).grid(  # type: ignore[arg-type]
            row=3, column=1, sticky="ew", pady=3
        )
        ttk.Spinbox(audio, from_=1, to=2, increment=1, textvariable=variables["gain"], width=6).grid(
            row=3, column=2, padx=(8, 0), pady=3
        )
        ttk.Label(audio, text="x").grid(row=3, column=3, sticky="w", padx=(4, 0), pady=3)

        performance = ttk.LabelFrame(left_col, text=ui("Akış Dayanıklılığı"), padding=8, style="Section.TLabelframe")
        performance.grid(row=2 + row_offset, column=0, sticky="ew", pady=(0, 8))
        performance.columnconfigure(1, weight=1)
        ttk.Label(performance, text=ui("Yakalama tamponu")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Scale(performance, from_=50, to=750, variable=variables["buffer_ms"], command=lambda value: variables["buffer_ms"].set(round(float(value)))).grid(  # type: ignore[arg-type]
            row=0, column=1, sticky="ew", pady=3
        )
        ttk.Spinbox(performance, from_=50, to=750, increment=50, textvariable=variables["buffer_ms"], width=6).grid(
            row=0, column=2, padx=(8, 0), pady=3
        )
        ttk.Label(performance, text="ms", style="Value.TLabel").grid(row=0, column=3, sticky="w", padx=(4, 0), pady=3)
        ttk.Label(performance, text=ui("RAOP gecikmesi")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Combobox(
            performance,
            textvariable=variables["latency_frames"],
            values=("1", "4410", "11025", "22050", "44100", "66150"),
            state="normal",
        ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(performance, text="frame", style="Value.TLabel").grid(row=1, column=3, sticky="w", padx=(4, 0), pady=3)
        ttk.Label(
            performance,
            text=ui("Anlık mod 1 karelik deneysel gecikmeyi kullanır. Sorun olursa diğer modlardan birini seç."),
            style="Hint.TLabel",
            wraplength=390,
        ).grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, 0))

        actions = ttk.LabelFrame(right_col, text=ui("Kontroller"), padding=8, style="Section.TLabelframe")
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        actions.columnconfigure((0, 1), weight=1)

        presets = ttk.LabelFrame(right_col, text=ui("Modlar"), padding=8, style="Section.TLabelframe")
        presets.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        presets.columnconfigure((0, 1), weight=1)

        tools = ttk.LabelFrame(advanced, text=ui("Dosyalar"), padding=12, style="Section.TLabelframe")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tools.columnconfigure((0, 1), weight=1)

        log_frame = ttk.LabelFrame(advanced, text=ui("Son Log"), padding=8, style="Section.TLabelframe")
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_box = tk.Text(log_frame, height=12, width=48, wrap="word", borderwidth=0, font=("Consolas", 8))
        log_box.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, command=log_box.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        log_box.configure(yscrollcommand=log_scroll.set)

        def detect() -> None:
            async def run_detect():
                return await discover_airplay_devices(timeout=6)

            try:
                found_devices = asyncio.run(run_detect())
                if not found_devices:
                    raise RuntimeError(ui("Yerel ağda uyumlu bir AirPlay alıcısı bulunamadı."))
                discovered_by_label.clear()
                for found in found_devices:
                    label = f"{found.name} — {found.address}"
                    discovered_by_label[label] = str(found.address)
                labels = list(discovered_by_label)
                target_box.configure(values=labels)
                variables["target"].set(labels[0])
                variables["address"].set(discovered_by_label[labels[0]])
                found_message = (
                    ui("AirPlay alıcısı bulundu.")
                    if len(labels) == 1
                    else f"{len(labels)} {ui('AirPlay alıcısı bulundu')}"
                )
                messagebox.showinfo(APP_NAME, found_message)
            except Exception as ex:
                messagebox.showerror(APP_NAME, str(ex))

        def select_target(_event=None) -> None:
            address = discovered_by_label.get(variables["target"].get())
            if address:
                variables["address"].set(address)

        target_box.bind("<<ComboboxSelected>>", select_target)

        def collect_config() -> dict:
            return {
                "address": variables["address"].get().strip(),
                "auto_detect": variables["auto_detect"].get(),
                "device": variables["device"].get().strip() or None,
                "volume": max(0, min(100, int(float(variables["volume"].get())))),
                "gain": max(1, min(2, int(float(variables["gain"].get())))),
                "buffer_ms": max(50, min(750, int(float(variables["buffer_ms"].get())))),
                "latency_frames": max(1, min(66150, int(float(variables["latency_frames"].get())))),
                "language": "tr" if variables["language"].get() == "Türkçe" else "en",
                "install_done": True,
                "setup_done": True,
            }

        def save(reconnect: bool = False) -> None:
            save_config(collect_config())
            log("Ayarlar kontrol panelinden kaydedildi")
            if reconnect:
                if self.runner.running:
                    self.runner.restart()
                else:
                    self.runner.start()

        def apply_live_audio(*_args) -> None:
            volume = max(0, min(100, int(float(variables["volume"].get()))))
            gain = max(1, min(2, int(float(variables["gain"].get()))))
            self.runner.apply_live_volume(volume)
            self.runner.apply_live_gain(gain)
            config_now = load_config()
            config_now["volume"] = volume
            config_now["gain"] = gain
            save_config(config_now)

        variables["volume"].trace_add("write", apply_live_audio)
        variables["gain"].trace_add("write", apply_live_audio)

        def apply_preset_to_form(name: str) -> None:
            for key, value in PRESETS[name].items():
                if key in variables:
                    variables[key].set(value)
            save(reconnect=self.runner.running)

        def restore_defaults() -> None:
            for key, value in DEFAULT_CONFIG.items():
                if key in variables:
                    variables[key].set(value if value is not None else "")
            variables["language"].set("Türkçe" if DEFAULT_CONFIG["language"] == "tr" else "English")
            config_now = dict(DEFAULT_CONFIG)
            config_now["install_done"] = True
            config_now["setup_done"] = True
            save_config(config_now)
            if self.runner.running:
                self.runner.restart()
            messagebox.showinfo(APP_NAME, ui("Varsayılanlara dönüldü."))

        def toggle_startup() -> None:
            try:
                set_startup_task(variables["startup"].get())
                message = ui("Windows ile başlatma açıldı") if variables["startup"].get() else ui("Windows ile başlatma kapatıldı")
                log(message)
            except Exception as ex:
                variables["startup"].set(startup_task_installed())
                messagebox.showerror(APP_NAME, str(ex))

        def refresh_log() -> None:
            try:
                lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-18:]
            except FileNotFoundError:
                lines = []
            log_box.configure(state="normal")
            log_box.delete("1.0", "end")
            log_box.insert("1.0", "\n".join(lines) if lines else ui("Henüz log yok."))
            log_box.configure(state="disabled")

        def refresh_status() -> None:
            detail = self.runner.detail or ui("Hazır")
            status_var.set(f"{tr_status(self.runner.status)} - {detail}")
            refresh_log()
            root.after(2500, refresh_status)

        def connect_from_panel() -> None:
            save(reconnect=True)

        def change_language(_event=None) -> None:
            language = "tr" if variables["language"].get() == "Türkçe" else "en"
            config_now = collect_config()
            config_now["language"] = language
            save_config(config_now)
            set_language(language)
            self.icon.menu = self._menu()
            self.icon.update_menu()
            root.destroy()
            self._open_settings()

        def modern_button(parent, text, command, primary=False):
            bg = "#16a34a" if primary else "#ffffff"
            fg = "#ffffff" if primary else "#111827"
            active_bg = "#15803d" if primary else "#e5e7eb"
            return tk.Button(
                parent,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                relief="flat",
                bd=0,
                padx=10,
                pady=8,
                font=("Segoe UI", 9, "bold" if primary else "normal"),
                cursor="hand2",
            )

        modern_button(actions, ui("Bağlan"), connect_from_panel, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=4)
        modern_button(actions, ui("Bağlantıyı Kes"), self._stop).grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=4)
        modern_button(actions, ui("Alıcıları Bul"), detect).grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Checkbutton(actions, text=ui("Windows ile başlat"), variable=variables["startup"], command=toggle_startup).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 4)
        )
        ttk.Label(actions, text=ui("Dil")).grid(row=3, column=0, sticky="w", pady=4)
        language_box = ttk.Combobox(actions, textvariable=variables["language"], values=("Türkçe", "English"), state="readonly", width=12)
        language_box.grid(row=3, column=1, sticky="ew", pady=4)
        language_box.bind("<<ComboboxSelected>>", change_language)
        ttk.Button(actions, text=ui("Varsayılanlara Dön"), command=restore_defaults, style="Tool.TButton").grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(presets, text=ui("Anlık"), command=lambda: apply_preset_to_form("instant"), style="Tool.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=4)
        ttk.Button(presets, text=ui("Tepkisel"), command=lambda: apply_preset_to_form("responsive"), style="Tool.TButton").grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=4)
        ttk.Button(presets, text=ui("Dengeli"), command=lambda: apply_preset_to_form("balanced"), style="Tool.TButton").grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=4)
        ttk.Button(presets, text=ui("Stabil"), command=lambda: apply_preset_to_form("stable"), style="Tool.TButton").grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=4)

        ttk.Button(tools, text=ui("Logu Aç"), command=lambda: self._open_path(LOG_PATH), style="Tool.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=4)
        ttk.Button(tools, text=ui("Ayar Dosyasını Aç"), command=lambda: self._open_path(CONFIG_PATH), style="Tool.TButton").grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=4)

        refresh_status()

        root.mainloop()

    def _refresh_menu(self) -> None:
        while not self.exit_event.wait(2):
            self._set_color()
            self.icon.title = f"{APP_NAME} - {tr_status(self.runner.status)}"
            self.icon.update_menu()

    def run(self, open_settings: bool = True) -> None:
        config = load_config()
        log("Tray app started")
        if not config.get("install_done", False):
            config["install_done"] = True
            save_config(config)
            log("First run initialized")
        if config.get("setup_done", False):
            self.runner.start()
        else:
            self.runner.detail = ui("İlk kurulum gerekli")
        self.menu_thread.start()
        if open_settings or not config.get("setup_done", False):
            self._open_settings()
        self.icon.run()


def acquire_lock():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, True, "Local\\AudioFerrySingleInstance")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK_PATH.open("w", encoding="utf-8")
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return mutex, lock_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream Windows system audio to AirPlay devices.")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--check-config", action="store_true", help="validate the configuration and exit")
    parser.add_argument("--minimized", action="store_true", help="start in the notification area without opening settings")
    args = parser.parse_args()

    if args.list_devices:
        print(list_audio_devices())
        return
    if args.check_config:
        print(json.dumps(load_config(), indent=2))
        return

    mutex, lock_file = acquire_lock()
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        TrayApp().run(open_settings=not args.minimized)
    finally:
        lock_file.close()
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(mutex)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        ERR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror(APP_NAME, f"Uygulama başlatılamadı:\n\n{ex}\n\nLog: {ERR_PATH}")
        except Exception:
            pass
        raise
