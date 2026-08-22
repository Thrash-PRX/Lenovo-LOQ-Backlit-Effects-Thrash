import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app


class DummyController:
    method = "lenovo_vantage_dll"

    def __init__(self):
        self.shutdown_calls = 0
        self.current_level = 0
        self.max_level = 2
        self.levels = []

    def get_status(self):
        return {
            "system_model": "TEST",
            "method_display": "Ready",
            "method": "lenovo_vantage_dll",
        }

    def shutdown(self):
        self.shutdown_calls += 1

    def set_brightness(self, level):
        self.current_level = level
        self.levels.append(level)
        return True


class DummyEngine:
    def __init__(self):
        self.running = False
        self.current_effect = None
        self.music_level = 0
        self.last_error = None
        self.idle_sleeping = False
        self.idle_seconds = 0
        self.stop_calls = 0
        self.stop_restore_values = []
        self.start_calls = []

    def start(self, effect, **kwargs):
        self.running = True
        self.current_effect = effect
        self.start_calls.append((effect, kwargs))

    def stop(self, restore=True):
        self.stop_calls += 1
        self.stop_restore_values.append(restore)
        self.running = False


class DesktopShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings_directory = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, cls.settings_directory.name)
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setQuitOnLastWindowClosed(False)

    @classmethod
    def tearDownClass(cls):
        cls.settings_directory.cleanup()

    def test_close_hides_to_tray_and_quit_cleans_up(self):
        controller = DummyController()
        engine = DummyEngine()
        window = app.DesktopApplication(controller, engine)
        window._tray_notice_shown = True
        window.show()
        self.qt_app.processEvents()

        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            window.close()
            self.qt_app.processEvents()

        self.assertFalse(window.isVisible())
        self.assertEqual(engine.stop_calls, 0)
        self.assertEqual(controller.shutdown_calls, 0)

        window._quit_application()
        self.assertEqual(engine.stop_calls, 1)
        self.assertEqual(controller.shutdown_calls, 1)

    def test_startup_state_requires_task_and_task_manager_entry(self):
        with patch.object(app, "_startup_task_exists", return_value=True), patch.object(
            app, "_startup_registry_enabled", return_value=True
        ):
            self.assertTrue(app.startup_task_enabled())
        with patch.object(app, "_startup_task_exists", return_value=True), patch.object(
            app, "_startup_registry_enabled", return_value=False
        ):
            self.assertFalse(app.startup_task_enabled())

    def test_enabling_startup_creates_task_before_run_entry(self):
        calls = []
        with patch.object(app, "_create_startup_task", side_effect=lambda: calls.append("task")), patch.object(
            app, "_set_startup_registry", side_effect=lambda enabled: calls.append(f"run:{enabled}")
        ):
            app.set_startup_task(True)
        self.assertEqual(calls, ["task", "run:True"])

    def test_normal_mode_hides_all_advanced_controls(self):
        window = app.DesktopApplication(DummyController(), DummyEngine())
        window.god_checkbox.setChecked(False)
        self.qt_app.processEvents()
        self.assertTrue(all(widget.isHidden() for widget in window.advanced_widgets))
        window._quit_application()

    def test_startup_battery_saver_starts_asleep(self):
        controller = DummyController()
        controller.levels = []
        controller.set_brightness = lambda level: controller.levels.append(level) or True
        engine = DummyEngine()
        window = app.DesktopApplication(controller, engine)
        window.arm_startup_battery_saver()
        self.assertEqual(controller.levels[-1], 0)
        self.assertEqual(engine.start_calls[-1][0], "battery_saver")
        self.assertTrue(engine.start_calls[-1][1]["start_asleep"])
        window._quit_application()

    def test_effect_cards_switch_immediately_with_one_click(self):
        engine = DummyEngine()
        controller = DummyController()
        window = app.DesktopApplication(controller, engine)
        window.cards["breathe"].click()
        self.assertEqual(engine.start_calls[-1][0], "breathe")
        window.cards["wave"].click()
        self.assertEqual(engine.start_calls[-1][0], "wave")
        self.assertEqual([call[0] for call in engine.start_calls[-2:]], ["breathe", "wave"])
        self.assertEqual(engine.stop_calls, 0)
        self.assertNotIn(0, controller.levels)
        self.assertTrue(window.power_button.property("powered"))
        window._quit_application()

    def test_selecting_effect_while_powered_off_starts_in_one_click(self):
        controller = DummyController()
        engine = DummyEngine()
        window = app.DesktopApplication(controller, engine)
        window.cards["breathe"].click()
        window.toggle_power()
        self.assertFalse(engine.running)
        controller.levels.clear()

        window.cards["wave"].click()

        self.assertTrue(engine.running)
        self.assertEqual(engine.start_calls[-1][0], "wave")
        self.assertTrue(window.power_button.property("powered"))
        self.assertNotIn(0, controller.levels)
        window._quit_application()

    def test_header_fits_full_title_at_minimum_and_normal_width(self):
        window = app.DesktopApplication(DummyController(), DummyEngine())
        window.show()

        for width in (1040, 1280):
            window.resize(width, 700)
            self.qt_app.processEvents()
            self.qt_app.processEvents()
            metrics = QFontMetrics(window.header_title.font())
            required = metrics.horizontalAdvance(window.header_title.text())
            available = window.header_title.contentsRect().width()
            self.assertLessEqual(required, available + 1, f"title clipped at {width}px")
            self.assertGreaterEqual(window.header_title.font().pointSizeF(), 15)
            self.assertLessEqual(
                window.header_panel.minimumSizeHint().width(),
                window.header_panel.width(),
            )
            self.assertTrue(window.power_button.isVisible())
            self.assertLessEqual(
                window.power_button.geometry().right(),
                window.header_panel.contentsRect().right(),
            )

        window._quit_application()

    def test_god_mode_reactive_choices_and_speed_apply_live(self):
        engine = DummyEngine()
        window = app.DesktopApplication(DummyController(), engine)
        window.god_mode = True
        window._apply_god_mode()
        window.cards["reactive"].click()

        window.react_buttons.button(5).click()
        window.hold_buttons.button(1).click()

        self.assertEqual(engine.mode, 5)
        self.assertEqual(engine.hold_behavior, 1)
        self.assertEqual(window.speed_slider.maximum(), 20)
        window.speed_slider.setValue(20)
        self.assertEqual(engine.speed, 2.0)

        window.cards["breathe"].click()
        self.assertEqual(window.speed_slider.maximum(), 16)
        self.assertLessEqual(engine.start_calls[-1][1]["speed"], 1.6)
        window._quit_application()

    def test_shell_uses_translucent_glass_surfaces(self):
        window = app.DesktopApplication(DummyController(), DummyEngine())
        self.assertIsInstance(window.header_panel, app.GlassFrame)
        self.assertIsInstance(window.sidebar_panel, app.GlassFrame)
        glass_surfaces = window.findChildren(app.GlassFrame)
        self.assertGreaterEqual(len(glass_surfaces), 5)
        self.assertTrue(
            all(surface.testAttribute(Qt.WA_TranslucentBackground) for surface in glass_surfaces)
        )
        self.assertFalse(window.background._texture.isNull())
        window._quit_application()

    def test_top_right_power_turns_keyboard_fully_off(self):
        controller = DummyController()
        engine = DummyEngine()
        window = app.DesktopApplication(controller, engine)
        window.cards["breathe"].click()
        window.toggle_power()
        self.assertFalse(engine.running)
        self.assertEqual(controller.current_level, 0)
        self.assertFalse(window.power_button.property("powered"))
        window._quit_application()


if __name__ == "__main__":
    unittest.main()
