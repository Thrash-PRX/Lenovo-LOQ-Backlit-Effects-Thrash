import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app


class DummyController:
    method = "lenovo_vantage_dll"

    def __init__(self):
        self.shutdown_calls = 0

    def get_status(self):
        return {
            "system_model": "TEST",
            "method_display": "Ready",
            "method": "lenovo_vantage_dll",
        }

    def shutdown(self):
        self.shutdown_calls += 1


class DummyEngine:
    running = False
    current_effect = None
    music_level = 0
    last_error = None
    idle_sleeping = False
    idle_seconds = 0

    def __init__(self):
        self.stop_calls = 0
        self.start_calls = []

    def start(self, effect, **kwargs):
        self.running = True
        self.current_effect = effect
        self.start_calls.append((effect, kwargs))

    def stop(self):
        self.stop_calls += 1


class DesktopShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setQuitOnLastWindowClosed(False)

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


if __name__ == "__main__":
    unittest.main()
