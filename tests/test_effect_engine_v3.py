import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import app


class RecordingController:
    def __init__(self):
        self.current_level = 0
        self.max_level = 2
        self.levels = []

    def set_brightness(self, level):
        self.current_level = level
        self.levels.append(level)
        return True


class EffectEngineV3Tests(unittest.TestCase):
    def test_public_modes_exclude_retired_flash_modes(self):
        ids = {effect["id"] for effect in app.EffectEngine.EFFECTS_META}
        self.assertTrue({"battery_saver", "breathe", "reactive", "music_speaker"} <= ids)
        self.assertTrue({"blink", "strobe", "sos", "lightning", "candle"}.isdisjoint(ids))

    def test_intensity_uses_temporal_blending_between_native_levels(self):
        controller = RecordingController()
        engine = app.EffectEngine(controller)
        levels = [engine._render_intensity(25) for _ in range(120)]
        self.assertAlmostEqual(sum(levels) / len(levels), 0.5, delta=0.03)
        levels = [engine._render_intensity(75) for _ in range(120)]
        self.assertAlmostEqual(sum(levels) / len(levels), 1.5, delta=0.03)

    def test_intensity_scales_for_one_level_white_backlights(self):
        controller = RecordingController()
        controller.max_level = 1
        engine = app.EffectEngine(controller)
        levels = [engine._render_intensity(40) for _ in range(100)]
        self.assertAlmostEqual(sum(levels) / len(levels), 0.4, delta=0.03)
        self.assertLessEqual(max(levels), 1)

    def test_recommended_speed_is_used_without_god_mode_override(self):
        controller = RecordingController()
        engine = app.EffectEngine(controller)
        engine._start_keyboard_hook = lambda: True
        engine._loop = lambda: None
        engine.start("reactive", intensity=73)
        self.assertEqual(engine.intensity, 73)
        self.assertEqual(engine.speed, app.EffectEngine.RECOMMENDED_SPEEDS["reactive"])
        engine.stop(restore=False)

    def test_battery_saver_defaults_to_thirty_seconds(self):
        engine = app.EffectEngine(RecordingController())
        self.assertEqual(engine.idle_timeout, 30.0)

    def test_breathe_curve_has_soft_symmetric_shoulders(self):
        samples = [app.EffectEngine._breathe_envelope(i / 100) for i in range(101)]
        self.assertAlmostEqual(samples[0], 0.0)
        self.assertAlmostEqual(samples[50], 1.0)
        self.assertAlmostEqual(samples[-1], 0.0, places=8)
        self.assertTrue(all(a <= b for a, b in zip(samples[:50], samples[1:51])))
        self.assertTrue(all(a >= b for a, b in zip(samples[50:100], samples[51:])))
        self.assertLess(max(abs(b - a) for a, b in zip(samples, samples[1:])), 0.04)

    def test_wave_curve_is_materially_different_from_breathe(self):
        phases = [index / 100 for index in range(101)]
        breathe = [app.EffectEngine._breathe_envelope(phase) for phase in phases]
        wave = [app.EffectEngine._wave_envelope(phase) for phase in phases]

        breathe_peak = max(range(len(breathe)), key=breathe.__getitem__) / 100
        wave_peak = max(range(len(wave)), key=wave.__getitem__) / 100
        mean_difference = sum(abs(a - b) for a, b in zip(breathe, wave)) / len(phases)

        self.assertGreaterEqual(breathe_peak, 0.45)
        self.assertLessEqual(breathe_peak, 0.55)
        self.assertGreaterEqual(wave_peak, 0.08)
        self.assertLessEqual(wave_peak, 0.30)
        self.assertGreater(mean_difference, 0.25)
        self.assertGreater(
            app.EffectEngine._wave_envelope(0.78),
            app.EffectEngine._wave_envelope(0.68) + 0.20,
        )

    def test_god_mode_speed_limits_protect_smooth_effects(self):
        self.assertEqual(app.EffectEngine.clamp_speed("breathe", 9.0), 1.65)
        self.assertEqual(app.EffectEngine.clamp_speed("wave", 9.0), 2.20)
        self.assertEqual(app.EffectEngine.clamp_speed("reactive", 9.0), 2.00)
        self.assertEqual(app.EffectEngine.clamp_speed("breathe", 0.01), 0.45)

    def test_key_identity_ignores_repeat_and_releases_after_last_key(self):
        engine = app.EffectEngine(RecordingController())
        key_a = (0x41, 30, 0)
        key_b = (0x41, 48, 1)

        self.assertTrue(engine._record_key_down(key_a, 0x41))
        self.assertFalse(engine._record_key_down(key_a, 0x41))
        self.assertEqual(engine._keypress_counter, 1)
        self.assertTrue(engine._record_key_down(key_b, 0x41))
        self.assertEqual(engine._keypress_counter, 2)

        engine._keyrelease_event.clear()
        self.assertFalse(engine._record_key_up(key_a))
        self.assertFalse(engine._keyrelease_event.is_set())
        self.assertTrue(engine._record_key_up(key_b))
        self.assertTrue(engine._keyrelease_event.is_set())

    def _run_reactive_scenario(self, hold_behavior, release_at=None, stop_at=0.70):
        """Drive Reactive with a deterministic clock and no worker thread."""
        engine = app.EffectEngine(RecordingController())
        engine.running = True
        engine.mode = 2
        engine.intensity = 80
        engine.speed = 2.0
        engine.hold_behavior = hold_behavior
        engine._keypress_counter = 1
        engine._pressed_keys = {(0x41, 30, 0)}

        now = [0.0]
        rendered = []

        def monotonic():
            return now[0]

        def wait(duration):
            now[0] += duration
            if release_at is not None and now[0] >= release_at:
                with engine._keys_lock:
                    engine._pressed_keys.clear()
            if now[0] >= stop_at:
                engine.running = False
                return True
            return False

        def render(value):
            rendered.append((now[0], value))
            return 0

        with patch.object(app.time, "monotonic", side_effect=monotonic), patch.object(
            engine, "_wait", side_effect=wait
        ), patch.object(engine, "_render_intensity", side_effect=render):
            engine._reactive()

        return rendered

    def test_reactive_hold_stays_active_until_key_release(self):
        rendered = self._run_reactive_scenario(hold_behavior=2, release_at=0.30)
        active_times = [timestamp for timestamp, value in rendered if value == 80]

        self.assertGreater(len(active_times), 20)
        self.assertGreaterEqual(max(active_times), 0.30)
        self.assertTrue(any(timestamp > 0.31 and value < 80 for timestamp, value in rendered))

    def test_reactive_single_pulse_finishes_while_key_remains_held(self):
        rendered = self._run_reactive_scenario(hold_behavior=1, release_at=None)
        active_times = [timestamp for timestamp, value in rendered if value == 80]
        first_fade = min(
            timestamp
            for timestamp, value in rendered
            if timestamp > 0 and 29 < value < 80
        )

        self.assertGreaterEqual(max(active_times), 0.14)
        self.assertLess(first_fade, 0.25)


if __name__ == "__main__":
    unittest.main()
