import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import audioferry_app as app


class ConfigTests(unittest.TestCase):
    def test_valid_config_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge_config.json"
            path.write_text(json.dumps({"volume": 42, "address": "192.0.2.10"}), encoding="utf-8")
            with patch.object(app, "CONFIG_PATH", path):
                config = app.load_config()
            self.assertEqual(config["volume"], 42)
            self.assertEqual(config["address"], "192.0.2.10")

    def test_invalid_settings_fall_back_or_are_clamped(self):
        config = app.validate_config(
            {"address": "not an ip", "volume": "loud", "gain": 99, "buffer_ms": -1, "latency_frames": -1}
        )
        self.assertEqual(config["address"], "")
        self.assertEqual(config["volume"], app.DEFAULT_CONFIG["volume"])
        self.assertEqual(config["gain"], 2)
        self.assertEqual(config["buffer_ms"], 50)
        self.assertEqual(config["latency_frames"], 1)

    def test_language_is_validated(self):
        self.assertEqual(app.validate_config({"language": "en"})["language"], "en")
        self.assertEqual(app.validate_config({"language": "unknown"})["language"], app.DEFAULT_CONFIG["language"])

    def test_malformed_json_is_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge_config.json"
            path.write_text("{broken", encoding="utf-8")
            with patch.object(app, "CONFIG_PATH", path), patch.object(app, "ERR_PATH", Path(directory) / "error.log"):
                config = app.load_config()
            self.assertEqual(config, app.DEFAULT_CONFIG)
            self.assertTrue(path.with_suffix(".bad.json").exists())

    def test_logs_are_rotated(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "bridge.log"
            log_path.write_text("x" * 32, encoding="utf-8")
            with patch.object(app, "LOG_PATH", log_path), patch.object(app, "MAX_LOG_BYTES", 16):
                app.log("next")
            self.assertTrue(log_path.with_name("bridge.log.1").exists())
            self.assertIn("next", log_path.read_text(encoding="utf-8"))


class DiscoveryTests(unittest.TestCase):
    def test_empty_device_list_is_safe(self):
        async def empty_scan(*_args, **_kwargs):
            return []

        with patch.object(app, "scan", empty_scan):
            result = asyncio.run(app.discover_receiver(timeout=0))
        self.assertIsNone(result)


class PresetTests(unittest.TestCase):
    def test_four_presets_use_bounded_latency_and_capture_buffer(self):
        self.assertEqual(set(app.PRESETS), {"instant", "responsive", "balanced", "stable"})
        for preset in app.PRESETS.values():
            self.assertEqual(set(preset), {"buffer_ms", "latency_frames"})
            self.assertGreaterEqual(preset["buffer_ms"], 50)
            self.assertLessEqual(preset["buffer_ms"], 750)
            self.assertGreaterEqual(preset["latency_frames"], 1)
            self.assertLessEqual(preset["latency_frames"], 66150)
        self.assertEqual(app.PRESETS["instant"], {"buffer_ms": 50, "latency_frames": 1})


class AudioFormatTests(unittest.TestCase):
    def test_raw_raop_latency_keeps_one_frame_mode_and_is_bounded(self):
        self.assertEqual(app.normalize_raop_latency_frames(1), 1)
        self.assertEqual(app.normalize_raop_latency_frames(11025), 11025)
        self.assertEqual(app.normalize_raop_latency_frames(999999), 66150)

    def test_capture_formats_include_windows_native_fallback(self):
        microphone = type("Microphone", (), {"channels": 6})()
        formats = app.capture_format_candidates(microphone, 44100, 2)
        self.assertEqual(formats[0], (44100, 6))
        self.assertIn((48000, 6), formats)
        self.assertIn((48000, 2), formats)

    def test_resampler_converts_48khz_to_airplay_rate_across_chunks(self):
        resampler = app.LinearAudioResampler(48000, 44100)
        signal = np.linspace(-1.0, 1.0, 4800, dtype=np.float32).reshape((-1, 1))
        first = resampler.process(signal[:2400])
        second = resampler.process(signal[2400:])
        output = np.concatenate((first, second))
        self.assertAlmostEqual(len(output), 4410, delta=2)
        self.assertEqual(output.shape[1], 1)
        self.assertTrue(np.all(np.diff(output[:, 0]) >= 0))

    def test_audio_capture_error_stops_reconnect_loop(self):
        runner = app.BridgeRunner()

        async def fail_capture(*_args, **_kwargs):
            raise app.AudioCaptureError("unsupported mix format")

        with patch.object(app, "stream_once", fail_capture):
            runner._worker()

        self.assertTrue(runner.stop_event.is_set())
        self.assertFalse(runner.running)
        self.assertEqual(runner.status, "Stopped")
        self.assertIn("unsupported mix format", runner.last_error)


class StartupTests(unittest.TestCase):
    def test_headless_version_startup(self):
        result = subprocess.run(
            [sys.executable, str(Path(app.__file__)), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(app.APP_VERSION, result.stdout)

    def test_source_startup_command_uses_python_and_script(self):
        with patch.object(app.sys, "frozen", False, create=True):
            command = app.startup_command()
        self.assertIn(str(Path(app.sys.executable).resolve()), command)
        self.assertIn(str(Path(app.__file__).resolve()), command)
        self.assertIn("--minimized", command)

    def test_english_translation(self):
        original = app.CURRENT_LANGUAGE
        try:
            app.set_language("en")
            self.assertEqual(app.ui("Bağlan"), "Connect")
            self.assertEqual(app.tr_status("Running"), "Connected")
        finally:
            app.set_language(original)


if __name__ == "__main__":
    unittest.main()
