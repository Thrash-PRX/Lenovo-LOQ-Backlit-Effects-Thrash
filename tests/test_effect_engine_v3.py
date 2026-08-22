import os
import unittest

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
        engine._start_keyboard_hook = lambda: None
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


if __name__ == "__main__":
    unittest.main()
