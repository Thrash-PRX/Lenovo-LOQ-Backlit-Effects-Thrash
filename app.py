"""
Keyboard Backlight Effects Controller for Lenovo laptops (IdeaPad / LOQ / Legion)
================================================================================
Interfaces with Lenovo Vantage's IdeaNotebookAddin DLLs to control keyboard backlight.
Uses a persistent PowerShell subprocess for low-latency command execution.
Includes a global keyboard hook to react to keystrokes in real-time.
"""

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes
import subprocess
import glob
import re
import random
import datetime
import queue
import math
import tempfile
from xml.sax.saxutils import escape as xml_escape
from PySide6.QtCore import (
    Qt, QTimer, QRectF, QPointF, QEasingCurve, QPropertyAnimation,
    QSettings, QVariantAnimation,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap,
    QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QCheckBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QRadioButton,
    QProgressBar, QScrollArea, QSizePolicy, QSlider, QStackedWidget,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

# Define hook-related types and signatures for ctypes
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

# Declare HHOOK type
if not hasattr(wintypes, 'HHOOK'):
    wintypes.HHOOK = wintypes.HANDLE

# Declare HOOKPROC to return c_void_p (64-bit on x64 systems) to prevent overflow crash!
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# Set up user32 and kernel32 signatures for pointer safety
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HMODULE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_void_p

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

# ---------------------------------------------------------------------------
#  Admin check & self-elevation
# ---------------------------------------------------------------------------

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


APP_VERSION = "3.1.1"
STARTUP_TASK_NAME = "Lenovo LOQ Backlit Effects - Thrash"
STARTUP_RUN_VALUE = "Lenovo LOQ Backlit Effects - Thrash"
STARTUP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _hidden_process_kwargs():
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _startup_task_exists():
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", STARTUP_TASK_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **_hidden_process_kwargs(),
        )
        return result.returncode == 0
    except OSError:
        return False


def _startup_run_command():
    schtasks = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "schtasks.exe"
    )
    return f'"{schtasks}" /Run /TN "{STARTUP_TASK_NAME}"'


def _startup_registry_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_RUN_VALUE)
        return STARTUP_TASK_NAME in str(value)
    except OSError:
        return False


def startup_task_enabled():
    """Return whether the Task Manager-visible startup launcher is complete."""
    return _startup_task_exists() and _startup_registry_enabled()


def _startup_action():
    if getattr(sys, "frozen", False):
        return sys.executable, "--startup", os.path.dirname(sys.executable)
    script = os.path.abspath(__file__)
    return sys.executable, f'"{script}" --startup', os.path.dirname(script)


def _create_startup_task():
    executable, arguments, working_dir = _startup_action()
    domain = os.environ.get("USERDOMAIN", "")
    username = os.environ.get("USERNAME", "")
    user_id = f"{domain}\\{username}" if domain else username
    task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Starts Lenovo LOQ Backlit Effects in the notification area.</Description></RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>{xml_escape(user_id)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{xml_escape(executable)}</Command>
      <Arguments>{xml_escape(arguments)}</Arguments>
      <WorkingDirectory>{xml_escape(working_dir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''
    xml_path = None
    try:
        handle, xml_path = tempfile.mkstemp(prefix="loq-startup-", suffix=".xml")
        os.close(handle)
        with open(xml_path, "w", encoding="utf-16") as xml_file:
            xml_file.write(task_xml)
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", STARTUP_TASK_NAME, "/XML", xml_path, "/F"],
            capture_output=True,
            text=True,
            check=False,
            **_hidden_process_kwargs(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Task Scheduler rejected the request").strip()
            raise RuntimeError(detail)
    finally:
        if xml_path:
            try:
                os.unlink(xml_path)
            except OSError:
                pass


def _set_startup_registry(enabled):
    import winreg
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_RUN_KEY) as key:
            winreg.SetValueEx(key, STARTUP_RUN_VALUE, 0, winreg.REG_SZ, _startup_run_command())
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, STARTUP_RUN_VALUE)
    except FileNotFoundError:
        pass


def set_startup_task(enabled):
    """Register an elevated on-demand task and a Task Manager startup entry."""
    if enabled:
        _create_startup_task()
        try:
            _set_startup_registry(True)
        except Exception:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", STARTUP_TASK_NAME, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                **_hidden_process_kwargs(),
            )
            raise
    else:
        _set_startup_registry(False)
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", STARTUP_TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            check=False,
            **_hidden_process_kwargs(),
        )
        if result.returncode != 0 and result.returncode != 1:
            detail = (result.stderr or result.stdout or "Task Scheduler rejected the request").strip()
            raise RuntimeError(detail)
    return enabled

# ---------------------------------------------------------------------------
#  Dynamic DLL path finder
# ---------------------------------------------------------------------------

def find_lenovo_dlls():
    """Locate the latest version of Lenovo Vantage's IdeaNotebookAddin DLLs."""
    paths = glob.glob(r"C:\ProgramData\Lenovo\Vantage\Addins\IdeaNotebookAddin\*\KeyboardContract.dll")
    if paths:
        def version_key(path):
            folder_name = os.path.basename(os.path.dirname(path))
            return tuple(int(part) for part in re.findall(r"\d+", folder_name))

        latest_contract = max(paths, key=version_key)
        folder = os.path.dirname(latest_contract)
        dlls = {
            "contract": latest_contract,
            "addin": os.path.join(folder, "IdeaNotebookAddin.dll"),
            "json": os.path.join(folder, "Newtonsoft.Json.dll")
        }
        if all(os.path.isfile(path) for path in dlls.values()):
            return dlls
    return None

# ---------------------------------------------------------------------------
#  Keyboard Backlight Controller via Persistent PowerShell
# ---------------------------------------------------------------------------

class KeyboardBacklightController:
    """Controls Lenovo keyboard backlight via IdeaNotebookAddin.dll using persistent PowerShell."""

    def __init__(self):
        self.method = None
        self.current_level = 2  # 0=off, 1=dim, 2=bright
        self.max_level = 2
        self.backlight_level_type = "Unknown"
        self.compatible_white_backlight = False
        self.contract_version = "Unknown"
        self._lock = threading.Lock()
        self.ps_proc = None
        self._ps_output = queue.Queue()
        self._admin = is_admin()
        self.system_model = self._get_system_model()
        self.last_error = None
        self.reconnect_count = 0
        self._shutdown = threading.Event()
        self._monitor_thread = None

        self.detect_method()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _get_system_model(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
                product = str(winreg.QueryValueEx(key, "SystemProductName")[0]).strip()
                try:
                    family = str(winreg.QueryValueEx(key, "SystemFamily")[0]).strip()
                except OSError:
                    family = ""
            if family and family.lower() not in ("to be filled by o.e.m.", "system product name"):
                return f"{family} ({product})" if product and product not in family else family
            return product
        except Exception:
            return "Lenovo Laptop"

    def detect_method(self):
        """Safely initialize or reinitialize the hidden Lenovo bridge."""
        with self._lock:
            return self._detect_method_unlocked()

    def _detect_method_unlocked(self):
        """Initialize the persistent controller. Caller holds _lock."""
        self.close_ps()
        self.method = "connecting"
        self.last_error = None
        dlls = find_lenovo_dlls()
        if dlls:
            try:
                self.contract_version = os.path.basename(os.path.dirname(dlls["contract"]))
                powershell = os.path.join(
                    os.environ.get("SystemRoot", r"C:\Windows"),
                    "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
                )
                self.ps_proc = subprocess.Popen(
                    [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._ps_output = queue.Queue()
                threading.Thread(target=self._read_ps_output, daemon=True).start()

                init_script = f"""
                [System.Reflection.Assembly]::LoadFrom('{dlls["contract"]}') | Out-Null
                [System.Reflection.Assembly]::LoadFrom('{dlls["json"]}') | Out-Null
                $asm = [System.Reflection.Assembly]::LoadFrom('{dlls["addin"]}')
                $agentType = $asm.GetType('IdeaNotebookAddin.IdeaNotebookAgent')
                $agent = $agentType.GetMethod('GetInstance', [System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Static).Invoke($null, $null)
                $setBacklightMethod = $agentType.GetMethods() | Where-Object {{ $_.Name -eq 'SetBacklight' -and $_.GetParameters().Count -eq 2 }}

                function Set-KbdBacklight([string]$level) {{
                    $status = $agentType.GetMethod('GetBacklightStatus', [System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Instance).Invoke($agent, $null)
                    $list = $status.GetType().GetProperty('List').GetValue($status)
                    $items = $list.GetType().GetProperty('Items').GetValue($list)
                    foreach ($item in $items) {{
                        $keyVal = $item.GetType().GetProperty('key').GetValue($item)
                        if ($keyVal -eq 'KeyboardBacklightStatus') {{
                            $item.GetType().GetProperty('value').SetValue($item, $level)
                        }}
                    }}
                    $req = New-Object Lenovo.Modern.Contracts.Keyboard.KeyboardSettingsRequest
                    $req.List = $list
                    $jsonPayload = [Newtonsoft.Json.JsonConvert]::SerializeObject($req)
                    $resp = $setBacklightMethod.Invoke($agent, @($jsonPayload, $null))
                    Write-Output "OK:$level"
                }}

                function Get-KbdBacklight {{
                    $status = $agentType.GetMethod('GetBacklightStatus', [System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Instance).Invoke($agent, $null)
                    $list = $status.GetType().GetProperty('List').GetValue($status)
                    $items = $list.GetType().GetProperty('Items').GetValue($list)
                    $level = 'Unknown'
                    $capability = 'Unknown'
                    foreach ($item in $items) {{
                        $keyVal = $item.GetType().GetProperty('key').GetValue($item)
                        $valueVal = $item.GetType().GetProperty('value').GetValue($item)
                        if ($keyVal -eq 'KeyboardBacklightStatus') {{ $level = [string]$valueVal }}
                        if ($keyVal -eq 'KeyboardBacklightLevel') {{ $capability = [string]$valueVal }}
                    }}
                    Write-Output "STATE:$level|$capability"
                }}
                """
                self.ps_proc.stdin.write(init_script + "\n")
                self.ps_proc.stdin.flush()

                state = self._query_backlight_unlocked()
                if state is None:
                    raise RuntimeError("Lenovo Vantage did not report a keyboard backlight state")
                level, capability = state
                if capability not in ("OneLevel", "TwoLevels"):
                    raise RuntimeError(
                        f"This build currently supports white Lenovo backlights only (reported: {capability})"
                    )
                self.current_level = level
                self.backlight_level_type = capability
                self.max_level = 1 if capability == "OneLevel" else 2
                self.compatible_white_backlight = True
                self.method = "lenovo_vantage_dll"
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"Error initializing Vantage DLL control: {e}")
                self.close_ps()
        else:
            self.last_error = "Lenovo Vantage keyboard DLLs were not found"

        self.method = "unavailable"
        self.compatible_white_backlight = False
        return False

    def _query_backlight_unlocked(self):
        """Return (native level, capability) without changing the keyboard."""
        if not self.ps_proc or self.ps_proc.poll() is not None:
            return None
        while True:
            try:
                self._ps_output.get_nowait()
            except queue.Empty:
                break
        try:
            self.ps_proc.stdin.write("Get-KbdBacklight\n")
            self.ps_proc.stdin.flush()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    response = self._ps_output.get(timeout=max(0.01, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if response.startswith("STATE:"):
                    payload = response[6:]
                    state_text, _, capability = payload.partition("|")
                    level_map = {"Off": 0, "DisabledOff": 0, "Level_1": 1, "Level_2": 2, "Auto": 1}
                    if state_text in level_map:
                        return level_map[state_text], capability or "Unknown"
            return None
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def refresh_native_brightness(self):
        """Poll Fn+Space/Vantage state without mutating it."""
        with self._lock:
            state = self._query_backlight_unlocked()
            if state is None:
                return None
            level, capability = state
            self.current_level = level
            self.backlight_level_type = capability
            return level

    def _send_command(self, level_str):
        """Send command to persistent PowerShell stdin."""
        if not self.ps_proc:
            return False
        try:
            if self.ps_proc.poll() is not None:
                return False
            while True:
                try:
                    self._ps_output.get_nowait()
                except queue.Empty:
                    break
            self.ps_proc.stdin.write(f"Set-KbdBacklight '{level_str}'\n")
            self.ps_proc.stdin.flush()
            deadline = time.monotonic() + 5.0
            expected = f"OK:{level_str}"
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:
                    response = self._ps_output.get(timeout=max(0.01, remaining))
                except queue.Empty:
                    break
                if response == expected:
                    return True
            return False
        except Exception as e:
            self.last_error = str(e)
            print(f"PowerShell communication error: {e}")
            return False

    def _monitor_loop(self):
        """Restore the hidden bridge if it is closed or crashes."""
        while not self._shutdown.wait(2.0):
            proc_dead = self.ps_proc is None or self.ps_proc.poll() is not None
            if self.method != "lenovo_vantage_dll" or proc_dead:
                if self._shutdown.is_set():
                    break
                if self.detect_method():
                    self.reconnect_count += 1
                else:
                    self._shutdown.wait(4.0)

    def _read_ps_output(self):
        """Continuously drain PowerShell output so a DLL error cannot deadlock the UI."""
        proc = self.ps_proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            self._ps_output.put(line.strip())

    def close_ps(self):
        """Properly close the PowerShell process."""
        if self.ps_proc:
            try:
                self.ps_proc.stdin.write("exit\n")
                self.ps_proc.stdin.flush()
                self.ps_proc.wait(timeout=2)
            except:
                try:
                    self.ps_proc.kill()
                except:
                    pass
            self.ps_proc = None

    def shutdown(self):
        """Permanently stop recovery and close the bridge."""
        self._shutdown.set()
        with self._lock:
            self.close_ps()

    def set_backlight(self, on):
        """Turn backlight fully on or off."""
        if on:
            self.set_brightness(self.max_level)
        else:
            self.set_brightness(0)

    def set_brightness(self, level):
        """Set brightness: 0=off, 1=dim, 2=bright."""
        level = max(0, min(level, self.max_level))
        with self._lock:
            success = False
            try:
                if self.method == "lenovo_vantage_dll":
                    level_map = {0: "Off", 1: "Level_1", 2: "Level_2"}
                    success = self._send_command(level_map[level])
                    if not success:
                        self.method = "unavailable"
            except Exception as e:
                self.last_error = str(e)
                self.method = "unavailable"
                print(f"Set brightness error: {e}")
            if success:
                self.current_level = level
            return success

    def get_status(self):
        names = {
            "lenovo_vantage_dll": "Lenovo bridge online",
            "connecting": "Connecting to Lenovo Vantage…",
            "unavailable": "Compatible Lenovo Vantage interface not found",
        }
        return {
            "method": self.method,
            "method_display": names.get(self.method, self.method),
            "current_level": self.current_level,
            "max_level": self.max_level,
            "backlight_level_type": self.backlight_level_type,
            "compatible_white_backlight": self.compatible_white_backlight,
            "contract_version": self.contract_version,
            "is_admin": self._admin,
            "system_model": self.system_model,
            "last_error": self.last_error,
            "reconnect_count": self.reconnect_count,
        }

# ---------------------------------------------------------------------------
#  Effects Engine
# ---------------------------------------------------------------------------

class EffectEngine:
    EFFECTS_META = [
        {"id": "battery_saver", "name": "Battery Saver", "icon": "◉",  "desc": "Wakes softly, sleeps after 30 seconds"},
        {"id": "breathe",   "name": "Breathe",        "icon": "◌",     "desc": "Fluid sine-curve breathing"},
        {"id": "heartbeat", "name": "Heartbeat",      "icon": "♥",     "desc": "Double-pulse heartbeat rhythm"},
        {"id": "disco",     "name": "Disco",          "icon": "✦",     "desc": "Random high-energy flashing"},
        {"id": "pulse",     "name": "Pulse",          "icon": "◍",     "desc": "Quick flash with a slow fade"},
        {"id": "binary",    "name": "Binary Clock",   "icon": "01",    "desc": "Encodes seconds in binary"},
        {"id": "wave",      "name": "Wave",           "icon": "≈",     "desc": "Rolling brightness crest"},
        {"id": "reactive",  "name": "Reactive",       "icon": "⌨",     "desc": "Brightens on every keypress"},
        {"id": "music_mic", "name": "Music / Mic",    "icon": "♪",     "desc": "Follows the default microphone"},
        {"id": "music_speaker", "name": "Music / Speaker", "icon": "♫", "desc": "Beat detection from speaker output"},
    ]

    RECOMMENDED_SPEEDS = {
        "battery_saver": 1.0,
        "breathe": 1.0,
        "heartbeat": 1.0,
        "disco": 0.72,
        "pulse": 1.0,
        "binary": 1.0,
        "wave": 0.9,
        "reactive": 1.0,
        "music_mic": 1.15,
        "music_speaker": 1.35,
    }

    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.running = False
        self.current_effect = None
        self.speed = 1.0
        self.intensity = 50
        self.mode = 2
        self.hold_behavior = 2
        self.idle_timeout = 30.0
        self.start_asleep = False
        self._rendered_intensity = 0.0
        self._pdm_error = 0.0
        self._stop = threading.Event()
        self._thread = None

        # Keyboard Hook fields
        self._hook_handle = None
        self._hook_thread = None
        self._hook_thread_id = None
        self._keypress_event = threading.Event()
        self._keyrelease_event = threading.Event()
        self._hook_proc = None
        self._pressed_keys = set()
        self._keys_lock = threading.Lock()
        self._music_stream = None
        self._music_floor = 0.01
        self._music_peak = 0.05
        self._speaker_meter = None
        self._speaker_device = None
        self._speaker_com_initialized = False
        self._speaker_fast = 0.0
        self._speaker_slow = 0.0
        self._speaker_deviation = 0.01
        self._speaker_last_beat = 0.0
        self._speaker_flash_until = 0.0
        self._speaker_glow_until = 0.0
        self._idle_started = time.monotonic()
        self._default_level = None
        self._last_key_vk = None
        self.idle_sleeping = False
        self.idle_seconds = 0.0
        self.music_level = 0.0
        self.last_error = None

    def start(self, effect, intensity=50, speed=None, mode=2, hold_behavior=2, start_asleep=False):
        valid_effects = {item["id"] for item in self.EFFECTS_META}
        if effect not in valid_effects:
            raise ValueError(f"Unknown effect: {effect}")
        self.stop(restore=False)
        self.current_effect = effect
        recommended = self.RECOMMENDED_SPEEDS.get(effect, 1.0)
        self.speed = max(0.1, min(recommended if speed is None else speed, 5.0))
        self.intensity = max(1, min(int(intensity), 100))
        self.mode = mode
        self.hold_behavior = hold_behavior
        self.start_asleep = bool(start_asleep)
        self.last_error = None
        self._music_floor = 0.01
        self._music_peak = 0.05
        self._speaker_fast = 0.0
        self._speaker_slow = 0.0
        self._speaker_deviation = 0.01
        self._speaker_last_beat = 0.0
        self._speaker_flash_until = 0.0
        self._speaker_glow_until = 0.0
        self._idle_started = time.monotonic()
        self._default_level = None
        self.idle_sleeping = self.start_asleep
        self.idle_seconds = 0.0
        self._rendered_intensity = 0.0
        self._pdm_error = 0.0
        self.music_level = 0.0
        with self._keys_lock:
            self._pressed_keys.clear()
        self.running = True
        self._stop.clear()

        # Reactive and battery-saving default modes both need global input.
        if self.current_effect in ("reactive", "battery_saver"):
            self._start_keyboard_hook()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, restore=True):
        self.running = False
        self._stop.set()

        # Terminate keyboard hook if active
        self._stop_keyboard_hook()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._close_music_stream()
        if restore:
            target = max(1, int(round((self.intensity / 100.0) * self.ctrl.max_level)))
            self.ctrl.set_brightness(min(self.ctrl.max_level, target))
        self.current_effect = None

    def _wait(self, secs):
        self._stop.wait(secs)
        return not self.running

    def _loop(self):
        fns = {
            "battery_saver": self._battery_saver,
            "breathe": self._breathe,
            "heartbeat": self._heartbeat,
            "disco": self._disco,
            "pulse": self._pulse,
            "binary": self._binary,
            "wave": self._wave, "reactive": self._reactive,
            "music_mic": self._music_mic,
            "music_speaker": self._music_speaker,
        }
        fn = fns.get(self.current_effect)
        if not fn:
            return
        try:
            while self.running:
                if fn():
                    break
        except Exception as exc:
            self.last_error = str(exc)
            print(f"Effect error: {exc}")
        finally:
            self._close_music_stream()
            self.running = False
            if not self._stop.is_set():
                target = max(1, int(round((self.intensity / 100.0) * self.ctrl.max_level)))
                self.ctrl.set_brightness(min(self.ctrl.max_level, target))

    # -- Keyboard Hook Management -------------------------------------------

    def _start_keyboard_hook(self):
        """Starts the low-level global Windows keyboard hook thread."""
        self._keypress_event.clear()
        self._hook_thread = threading.Thread(target=self._hook_message_loop, daemon=True)
        self._hook_thread.start()

    def _stop_keyboard_hook(self):
        """Terminates the hook loop and removes the global hook."""
        if self._hook_thread_id:
            user32.PostThreadMessageW(self._hook_thread_id, 0x0012, 0, 0) # WM_QUIT
        if (self._hook_thread and self._hook_thread.is_alive()
                and self._hook_thread is not threading.current_thread()):
            self._hook_thread.join(timeout=1)
        self._keypress_event.clear()

    def _hook_message_loop(self):
        """Standard Windows message loop that handles keyboard events."""
        self._hook_thread_id = kernel32.GetCurrentThreadId()
        def hook_cb(nCode, wParam, lParam):
            try:
                if nCode >= 0 and self.running:
                    kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = kbd.vkCode

                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._last_key_vk = vk
                        with self._keys_lock:
                            is_repeat = vk in self._pressed_keys
                            if not is_repeat:
                                self._pressed_keys.add(vk)
                        self._keypress_event.set()
                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        with self._keys_lock:
                            self._pressed_keys.discard(vk)
                            if len(self._pressed_keys) == 0:
                                self._keyrelease_event.set()
            except Exception as e:
                print(f"Keyboard hook exception: {e}")
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # Keep a reference to prevent GC crash
        self._hook_proc = HOOKPROC(hook_cb)
        hmod = kernel32.GetModuleHandleW(None)

        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc,
            hmod,
            0
        )

        if not self._hook_handle:
            print(f"Global Keyboard Hook failed! Error: {kernel32.GetLastError()}")
            return

        msg = wintypes.MSG()
        while self.running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
        self._hook_handle = None
        self._hook_thread_id = None

    # -- Effects ------------------------------------------------------------

    def _render_intensity(self, percent):
        """Render a perceived 0-100 intensity across the three native levels."""
        percent = max(0.0, min(100.0, float(percent)))
        self._rendered_intensity = percent
        maximum = max(1, int(getattr(self.ctrl, "max_level", 2)))
        target = (percent / 100.0) * maximum
        base = min(maximum, int(math.floor(target)))
        fraction = max(0.0, target - base)
        level = base
        if base < maximum and fraction > 0:
            self._pdm_error += fraction
            if self._pdm_error >= 1.0:
                level = base + 1
                self._pdm_error -= 1.0
        if level != self.ctrl.current_level:
            self.ctrl.set_brightness(level)
        return level

    def _fade_to(self, target, duration=0.55, start=None):
        """Perceptually smooth transition using sine easing and pulse-density blending."""
        start = self._rendered_intensity if start is None else float(start)
        target = max(0.0, min(100.0, float(target)))
        started = time.monotonic()
        duration = max(0.05, float(duration))
        while self.running:
            progress = min(1.0, (time.monotonic() - started) / duration)
            eased = 0.5 - 0.5 * math.cos(math.pi * progress)
            self._render_intensity(start + (target - start) * eased)
            if progress >= 1.0:
                return False
            if self._wait(1.0 / 60.0):
                return True
        return True

    def _battery_saver(self):
        """Wake softly to remembered intensity and sleep after 30 idle seconds."""
        if self._keypress_event.is_set():
            self._keypress_event.clear()
            if self._last_key_vk == 0x20 and not self.idle_sleeping:
                # Fn itself is firmware-owned, but Space is visible. Give the
                # native Fn+Space cycle time to settle, then synchronize.
                previous_native = self.ctrl.current_level
                if self._wait(0.07):
                    return True
                native = self.ctrl.refresh_native_brightness()
                if native is not None and native != previous_native:
                    self.intensity = max(1, int(round((native / self.ctrl.max_level) * 100)))
            self._idle_started = time.monotonic()
            self.idle_seconds = 0.0
            if self.idle_sleeping:
                self.idle_sleeping = False
                if self._fade_to(self.intensity, 0.68, start=0):
                    return True

        self.idle_seconds = max(0.0, time.monotonic() - self._idle_started)
        if self.idle_seconds >= self.idle_timeout and not self.idle_sleeping:
            self.idle_sleeping = True
            if self._fade_to(0, 0.48):
                return True

        if self.idle_sleeping:
            if self.ctrl.current_level != 0:
                self.ctrl.set_brightness(0)
            return self._wait(0.05)

        self._render_intensity(self.intensity)
        return self._wait(1.0 / 60.0)

    def _breathe(self):
        """Continuous sine breathing rendered at 60 Hz over native levels."""
        cycle = 4.2 / self.speed
        started = time.monotonic()
        while self.running:
            phase = ((time.monotonic() - started) % cycle) / cycle
            envelope = 0.5 - 0.5 * math.cos(phase * math.tau)
            # A small gamma lift avoids spending too long visually black.
            envelope = envelope ** 0.72
            self._render_intensity(self.intensity * envelope)
            if self._wait(1.0 / 60.0):
                return True
        return True

    def _heartbeat(self):
        b, p, r = 0.12 / self.speed, 0.15 / self.speed, 0.7 / self.speed
        self._render_intensity(self.intensity)
        if self._wait(b): return True
        self._render_intensity(0)
        if self._wait(p): return True
        self._render_intensity(self.intensity)
        if self._wait(b): return True
        self._render_intensity(0)
        if self._wait(r): return True

    def _disco(self):
        self._render_intensity(self.intensity)
        if self._wait(random.uniform(0.04, 0.25) / self.speed): return True
        self._render_intensity(0)
        if self._wait(random.uniform(0.04, 0.25) / self.speed): return True

    def _pulse(self):
        if self._fade_to(self.intensity, 0.10 / self.speed, start=0): return True
        if self._fade_to(0, 0.72 / self.speed, start=self.intensity): return True
        if self._wait(0.18 / self.speed): return True

    def _binary(self):
        bits = format(datetime.datetime.now().second, "06b")
        for b in bits:
            if not self.running: return True
            self._render_intensity(self.intensity if b == "1" else 0)
            if self._wait(0.35 / self.speed): return True
        self._render_intensity(0)
        if self._wait(0.6 / self.speed): return True

    def _wave(self):
        """A quicker asymmetric rolling crest for a single-zone keyboard."""
        cycle = 2.8 / self.speed
        started = time.monotonic()
        while self.running:
            phase = ((time.monotonic() - started) % cycle) / cycle
            if phase < 0.32:
                envelope = math.sin((phase / 0.32) * math.pi / 2) ** 1.4
            else:
                envelope = max(0.0, math.cos(((phase - 0.32) / 0.68) * math.pi / 2)) ** 2.2
            self._render_intensity(self.intensity * envelope)
            if self._wait(1.0 / 60.0):
                return True
        return True

    def _music_mic(self):
        """Map default-microphone loudness to the keyboard's three brightness levels."""
        if self._music_stream is None:
            try:
                import sounddevice as sd
            except ImportError as exc:
                raise RuntimeError("Music mode requires the bundled sounddevice component") from exc
            try:
                self._music_stream = sd.RawInputStream(
                    samplerate=44100,
                    blocksize=1024,
                    channels=1,
                    dtype="int16",
                )
                self._music_stream.start()
            except Exception as exc:
                self._close_music_stream()
                raise RuntimeError(f"Could not open the default microphone: {exc}") from exc

        data, _overflowed = self._music_stream.read(1024)
        samples = memoryview(data).cast("h")
        if not samples:
            return False

        mean_square = sum(sample * sample for sample in samples) / len(samples)
        rms = (mean_square ** 0.5) / 32768.0
        self._apply_music_intensity(rms)
        return False

    def _music_speaker(self):
        """Detect beat-like output transients without opening the microphone."""
        if self._speaker_meter is None:
            try:
                from ctypes import POINTER, cast
                import comtypes
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

                comtypes.CoInitialize()
                self._speaker_com_initialized = True
                self._speaker_device = AudioUtilities.GetSpeakers()
                interface = self._speaker_device._dev.Activate(
                    IAudioMeterInformation._iid_, CLSCTX_ALL, None
                )
                self._speaker_meter = cast(interface, POINTER(IAudioMeterInformation))
            except Exception as exc:
                self._close_music_stream()
                raise RuntimeError(f"Could not monitor Windows speaker output: {exc}") from exc

        peak = float(self._speaker_meter.GetPeakValue())
        self._apply_speaker_beat(peak)
        return self._wait(0.020)

    def _apply_speaker_beat(self, raw_level, now=None):
        """Turn endpoint peaks into adaptive, debounced beat pulses."""
        now = time.monotonic() if now is None else float(now)
        raw_level = max(0.0, min(1.0, float(raw_level)))

        # The fast envelope follows drum attacks; the slow envelope tracks the
        # song's current loudness. Their separation is an onset, not just volume.
        self._speaker_fast = self._speaker_fast * 0.48 + raw_level * 0.52
        self._speaker_slow = self._speaker_slow * 0.94 + raw_level * 0.06
        onset = max(0.0, self._speaker_fast - self._speaker_slow)
        self._speaker_deviation = self._speaker_deviation * 0.94 + onset * 0.06

        sensitivity = max(0.2, min(4.0, self.speed))
        threshold = (
            0.006 + self._speaker_slow * 0.15 + self._speaker_deviation * 1.10
        ) / (0.72 + sensitivity * 0.34)
        refractory = max(0.095, 0.24 - sensitivity * 0.028)
        is_beat = (
            raw_level >= 0.018
            and onset >= threshold
            and now - self._speaker_last_beat >= refractory
        )

        if is_beat:
            self._speaker_last_beat = now
            self._speaker_flash_until = now + 0.075
            self._speaker_glow_until = now + 0.19

        if now < self._speaker_flash_until:
            output_intensity = self.intensity
            target_meter = 1.0
        elif now < self._speaker_glow_until:
            output_intensity = self.intensity * 0.48
            target_meter = 0.48
        else:
            output_intensity = 0
            target_meter = min(0.28, raw_level * 1.8)

        self.music_level = self.music_level * 0.34 + target_meter * 0.66
        self._render_intensity(output_intensity)
        return is_beat

    def _apply_music_intensity(self, raw_level):
        """Normalize either microphone RMS or speaker peak into three hardware levels."""
        raw_level = max(0.0, min(1.0, float(raw_level)))

        # Slowly learn the room noise floor and decay the recent peak. This keeps
        # the three available backlight levels responsive across different sources.
        if raw_level < self._music_floor * 1.8:
            self._music_floor = self._music_floor * 0.98 + raw_level * 0.02
        self._music_peak = max(raw_level, self._music_peak * 0.965, self._music_floor + 0.015)
        span = max(0.015, self._music_peak - self._music_floor)
        sensitivity = 0.65 + self.speed * 0.55
        intensity = max(0.0, min(1.0, ((raw_level - self._music_floor) / span) * sensitivity))
        self.music_level = self.music_level * 0.45 + intensity * 0.55

        self._render_intensity(self.intensity * self.music_level)

    def _close_music_stream(self):
        stream = self._music_stream
        self._music_stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._speaker_meter = None
        self._speaker_device = None
        if self._speaker_com_initialized:
            try:
                import comtypes
                comtypes.CoUninitialize()
            except Exception:
                pass
            self._speaker_com_initialized = False
        self.music_level = 0.0

    def _reactive(self):
        """Recommended default: dim idle, bright press, smooth release."""
        m = str(self.mode)
        if m == "2":
            base, active = self.intensity * 0.36, self.intensity
        elif m == "3":
            base, active = self.intensity, self.intensity * 0.40
        elif m == "4":
            base, active = 0, self.intensity * 0.55
        elif m == "5":
            base, active = 0, self.intensity
        else:
            base, active = self.intensity, 0

        self._render_intensity(base)
        self._keypress_event.clear()
        self._keyrelease_event.clear()

        if self._keypress_event.wait(timeout=0.2):
            self._render_intensity(active)

            if str(self.hold_behavior) == "2":
                if self._wait(0.075 / self.speed):
                    return True

                with self._keys_lock:
                    keys_held = len(self._pressed_keys) > 0

                while keys_held and self.running:
                    self._keyrelease_event.wait(timeout=0.2)
                    with self._keys_lock:
                        keys_held = len(self._pressed_keys) > 0

                self._keypress_event.clear()
                self._keyrelease_event.clear()
                if self._fade_to(base, 0.26 / self.speed, start=active):
                    return True
            else:
                if self._wait(0.11 / self.speed):
                    return True
                self._keypress_event.clear()
                if self._fade_to(base, 0.22 / self.speed, start=active):
                    return True

    def get_status(self):
        return {
            "running": self.running,
            "current_effect": self.current_effect,
            "speed": self.speed,
            "intensity": self.intensity,
            "idle_timeout": self.idle_timeout,
            "music_level": self.music_level,
            "idle_sleeping": self.idle_sleeping,
            "idle_seconds": self.idle_seconds,
            "last_error": self.last_error,
        }

# ---------------------------------------------------------------------------
#  Native Windows desktop interface
# ---------------------------------------------------------------------------

controller = None
engine = None
window = None


class EffectCard(QAbstractButton):
    """A modern two-line lighting-mode card with consistent monochrome icons."""

    def __init__(self, effect, parent=None):
        super().__init__(parent)
        self.effect = effect
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(68)
        self.setToolTip(effect["desc"])
        self.setAccessibleName(effect["name"])
        self.setAccessibleDescription(effect["desc"])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        god_mode = bool(getattr(self.window(), "god_mode", False))

        if self.isChecked():
            background = QLinearGradient(rect.topLeft(), rect.bottomRight())
            background.setColorAt(0.0, QColor("#4b1018") if god_mode else QColor("#123a51"))
            background.setColorAt(1.0, QColor("#21090e") if god_mode else QColor("#0b2638"))
            border = QColor("#ff4d5f") if god_mode else QColor("#55c9ff")
            name_color = QColor("#f5fbff")
            desc_color = QColor("#ffc0c7") if god_mode else QColor("#a9daf2")
            icon_color = QColor("#ff6575") if god_mode else QColor("#67d3ff")
        elif self.underMouse():
            background = QColor(23, 36, 53, 248)
            border = QColor(62, 115, 153)
            name_color = QColor("#f3f8fc")
            desc_color = QColor("#aebfd0")
            icon_color = QColor("#75d6ff")
        else:
            background = QColor(15, 24, 37, 238)
            border = QColor(66, 89, 116, 135)
            name_color = QColor("#e8f0f7")
            desc_color = QColor("#8fa3b8")
            icon_color = QColor("#5fc9f5")

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 14, 14)

        icon_rect = QRectF(rect.left() + 15, rect.top() + 13, 28, 42)
        painter.setFont(QFont("Segoe UI Symbol", 14, QFont.DemiBold))
        painter.setPen(icon_color)
        painter.drawText(icon_rect, Qt.AlignLeft | Qt.AlignVCenter, self.effect["icon"])

        text_left = rect.left() + 49
        name_rect = QRectF(text_left, rect.top() + 12, rect.width() - 62, 22)
        desc_rect = QRectF(text_left, rect.top() + 34, rect.width() - 62, 21)
        painter.setFont(QFont("Segoe UI Variable Text", 9, QFont.DemiBold))
        painter.setPen(name_color)
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, self.effect["name"])
        painter.setFont(QFont("Segoe UI Variable Text", 7.8, QFont.Normal))
        painter.setPen(desc_color)
        painter.drawText(desc_rect, Qt.AlignLeft | Qt.AlignVCenter, self.effect["desc"])
        painter.end()


class AmbientBackground(QWidget):
    """Animated, resolution-independent background drawn directly by Qt."""

    def __init__(self):
        super().__init__()
        self.setObjectName("central")
        self._texture = QPixmap(resource_path(os.path.join("assets", "thrash-liquid-glass-v3.png")))
        self._started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(40)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        phase = time.monotonic() - self._started

        base = QLinearGradient(0, 0, width, height)
        base.setColorAt(0.0, QColor("#05070d"))
        base.setColorAt(0.52, QColor("#0a101b"))
        base.setColorAt(1.0, QColor("#070a11"))
        painter.fillRect(self.rect(), base)

        if not self._texture.isNull():
            scaled = self._texture.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            source_x = max(0, (scaled.width() - width) // 2)
            source_y = max(0, (scaled.height() - height) // 2)
            painter.setOpacity(0.42)
            painter.drawPixmap(0, 0, scaled, source_x, source_y, width, height)
            painter.setOpacity(1.0)

        for x, y, radius, color in [
            (width * (0.17 + 0.025 * math.sin(phase * 0.45)), height * 0.10,
             width * 0.52, QColor(0, 151, 255, 58)),
            (width * 0.92, height * (0.66 + 0.035 * math.cos(phase * 0.38)),
             width * 0.48, QColor(110, 56, 255, 40)),
        ]:
            glow = QRadialGradient(QPointF(x, y), radius)
            glow.setColorAt(0.0, color)
            fade = QColor(color)
            fade.setAlpha(0)
            glow.setColorAt(1.0, fade)
            painter.fillRect(self.rect(), glow)

        # A quiet keyboard-grid motif in the lower background.
        painter.setPen(QPen(QColor(96, 165, 250, 15), 1))
        key_w, key_h, gap = 42, 15, 7
        start_x, start_y = width * 0.43, height * 0.78
        for row in range(4):
            offset = (row % 2) * 12
            for col in range(11):
                rect = QRectF(start_x + col * (key_w + gap) + offset,
                              start_y + row * (key_h + gap), key_w, key_h)
                painter.drawRoundedRect(rect, 4, 4)

        painter.end()


class BootSplash(QWidget):
    """Original LOQ-inspired boot sequence with no copied Lenovo assets."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(720, 420)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.started = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        elapsed = time.monotonic() - self.started
        progress = min(1.0, elapsed / 2.4)
        eased = 1.0 - (1.0 - progress) ** 3

        panel = QRectF(4, 4, self.width() - 8, self.height() - 8)
        bg = QLinearGradient(panel.topLeft(), panel.bottomRight())
        bg.setColorAt(0, QColor("#04060b"))
        bg.setColorAt(0.55, QColor("#09111e"))
        bg.setColorAt(1, QColor("#04060b"))
        painter.setPen(QPen(QColor(63, 178, 255, int(110 * eased)), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(panel, 26, 26)

        glow = QRadialGradient(QPointF(self.width() / 2, self.height() * 0.42), 250)
        glow.setColorAt(0, QColor(31, 155, 255, int(105 * eased)))
        glow.setColorAt(1, QColor(31, 155, 255, 0))
        painter.fillRect(panel, glow)

        logo_font = QFont("Segoe UI Variable Display", 58, QFont.Bold)
        logo_font.setLetterSpacing(QFont.AbsoluteSpacing, 7)
        painter.setFont(logo_font)
        painter.setPen(QColor(235, 247, 255, int(255 * eased)))
        painter.drawText(QRectF(0, 105, self.width(), 100), Qt.AlignCenter, "LOQ")

        slash_x = self.width() / 2 + 86
        painter.setPen(QPen(QColor(56, 189, 248, int(255 * eased)), 5))
        painter.drawLine(int(slash_x - 12), 128, int(slash_x + 12), 184)

        sub_alpha = int(255 * max(0, min(1, (progress - 0.28) / 0.4)))
        painter.setFont(QFont("Segoe UI Variable Text", 10, QFont.Medium))
        painter.setPen(QColor(164, 205, 231, sub_alpha))
        painter.drawText(QRectF(0, 213, self.width(), 34), Qt.AlignCenter,
                         "BACKLIT EFFECTS  •  BY THRASH")

        track = QRectF(160, 292, 400, 3)
        painter.fillRect(track, QColor(255, 255, 255, 20))
        painter.fillRect(QRectF(track.left(), track.top(), track.width() * progress, track.height()),
                         QColor("#38bdf8"))
        painter.setFont(QFont("Segoe UI Variable Text", 8))
        painter.setPen(QColor(117, 146, 167, sub_alpha))
        painter.drawText(QRectF(0, 314, self.width(), 28), Qt.AlignCenter,
                         "INITIALIZING LENOVO LIGHTING BRIDGE")
        painter.end()


class DesktopApplication(QMainWindow):
    """Qt desktop interface; no web server or browser is involved."""

    def __init__(self, ctrl, effect_engine):
        super().__init__()
        self.ctrl = ctrl
        self.engine = effect_engine
        self.light_on = True
        self.effect_buttons = QButtonGroup(self)
        self.react_buttons = QButtonGroup(self)
        self.hold_buttons = QButtonGroup(self)
        self._shown_error = None
        self._entrance_animation = None
        self._has_animated = False
        self._quitting = False
        self._tray_notice_shown = False
        self._build_ui()
        self._build_tray()
        self._effect_changed()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(500)
        self._refresh_status()

    def _build_tray(self):
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip("Lenovo LOQ Backlit Effects - Thrash")
        tray_menu = QMenu()
        open_action = QAction("Open Lenovo LOQ Backlit Effects", self)
        open_action.triggered.connect(self._restore_from_tray)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(open_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_application(self):
        self._quitting = True
        self.status_timer.stop()
        self.engine.stop()
        self.ctrl.shutdown()
        self.tray_icon.hide()
        QApplication.instance().quit()

    def _build_ui(self):
        self.setWindowTitle("Lenovo LOQ Backlit Effects - Thrash")
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "app-icon.png"))))
        self.resize(1180, 900)
        self.setMinimumSize(980, 780)
        self.setStyleSheet("""
            QMainWindow { background: #05070d; }
            QWidget { color: #e7eef5; font: 9.5pt 'Segoe UI Variable Text'; }
            QLabel { background: transparent; color: #f1f5f9; }
            QLabel#eyebrow { color: #55c9ff; font: 600 8pt 'Segoe UI Variable Text'; letter-spacing: 2px; }
            QLabel#title { font: 650 27pt 'Segoe UI Variable Display'; color: #f8fbff; }
            QLabel#subtitle, QLabel#section, QLabel#hint { color: #94a3b8; }
            QLabel#section { font: 600 8pt 'Segoe UI Variable Text'; letter-spacing: 1.5px; }
            QFrame#brandChip { background: rgba(14, 31, 46, 225); border: 1px solid #24516d;
                               border-radius: 14px; }
            QLabel#brandMark { color: #56c9ff; font: 700 15pt 'Segoe UI Variable Display'; }
            QLabel#brandWord { color: #d8e8f3; font: 600 8pt 'Segoe UI Variable Text'; letter-spacing: 1px; }
            QLabel#connectionDot { color: #2dd4bf; font-size: 15px; }
            QFrame#panel, QGroupBox { background: rgba(14, 20, 31, 232);
                                     border: 1px solid rgba(94, 129, 163, 72); border-radius: 17px; }
            QFrame#notice { background: rgba(11, 31, 45, 210); border: 1px solid rgba(63, 142, 184, 90);
                            border-radius: 12px; }
            QGroupBox { margin-top: 10px; padding: 14px 10px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #94a3b8; padding: 0 5px; }
            QRadioButton { background: transparent; padding: 8px; }
            QRadioButton:hover { color: #67c5ff; }
            QCheckBox { spacing: 9px; color: #b7c8d8; padding: 4px; }
            QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #4c6680;
                                   border-radius: 5px; background: #0c1521; }
            QCheckBox::indicator:checked { background: #38bdf8; border-color: #70d5ff; }
            QPushButton { background: rgba(31, 42, 58, 235); border: 1px solid rgba(95, 123, 153, 45);
                          border-radius: 11px; padding: 11px 17px; font: 600 8.5pt 'Segoe UI Variable Text'; }
            QPushButton:hover { background: rgba(42, 58, 80, 245); border-color: rgba(94, 186, 238, 100); }
            QPushButton#start { background: #38bdf8; color: #041019; font: 700 9pt 'Segoe UI Variable Text'; border: 0; }
            QPushButton#start:hover { background: #7dd3fc; }
            QPushButton#start[running="true"] { background: #fb7185; color: #19070a; }
            QSlider::groove:horizontal { height: 5px; background: #263349; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #168ec5; border-radius: 2px; }
            QSlider::handle:horizontal { width: 20px; margin: -8px 0; background: #7dd3fc;
                                         border: 2px solid #0b3950; border-radius: 10px; }
            QProgressBar { height: 7px; background: #222a38; border: 0; border-radius: 3px; }
            QProgressBar::chunk { background: #38bdf8; border-radius: 3px; }
        """)

        central = AmbientBackground()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 25, 30, 26)
        layout.setSpacing(15)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        eyebrow = QLabel("LENOVO LOQ  /  NATIVE WINDOWS")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Backlit Effects")
        title.setObjectName("title")
        subtitle = QLabel("Precision control for your single-zone keyboard")
        subtitle.setObjectName("subtitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)

        brand = QFrame()
        brand.setObjectName("brandChip")
        brand.setFixedSize(126, 50)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(13, 6, 13, 6)
        brand_layout.setSpacing(9)
        brand_mark = QLabel("T/")
        brand_mark.setObjectName("brandMark")
        brand_word = QLabel("THRASH")
        brand_word.setObjectName("brandWord")
        brand_layout.addWidget(brand_mark)
        brand_layout.addWidget(brand_word)
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(brand, 0, Qt.AlignVCenter)
        layout.addLayout(header)

        status_panel = QFrame()
        status_panel.setObjectName("panel")
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 12, 16, 12)
        self.connection_dot = QLabel("●")
        self.connection_dot.setObjectName("connectionDot")
        self.method_label = QLabel("Detecting Lenovo lighting bridge…")
        self.state_label = QLabel("Ready")
        self.state_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_layout.addWidget(self.connection_dot)
        status_layout.addWidget(self.method_label, 1)
        status_layout.addWidget(self.state_label)
        layout.addWidget(status_panel)

        effects_panel = QFrame()
        effects_panel.setObjectName("panel")
        effects_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        effects_layout = QVBoxLayout(effects_panel)
        effects_layout.setContentsMargins(16, 15, 16, 16)
        section = QLabel("LIGHTING MODES")
        section.setObjectName("section")
        section.setFixedHeight(20)
        effects_layout.addWidget(section)

        grid_widget = QWidget()
        grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid = QGridLayout()
        grid_widget.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for index, effect in enumerate(EffectEngine.EFFECTS_META):
            button = EffectCard(effect)
            button.setProperty("effect_id", effect["id"])
            self.effect_buttons.addButton(button, index)
            grid.addWidget(button, index // 4, index % 4)
            if effect["id"] == "default":
                button.setChecked(True)
        self.effect_buttons.buttonClicked.connect(self._effect_changed)
        effects_layout.addWidget(grid_widget)

        self.speed_header_widget = QWidget()
        self.speed_header_widget.setFixedHeight(24)
        speed_header = QHBoxLayout(self.speed_header_widget)
        speed_header.setContentsMargins(0, 0, 0, 0)
        self.speed_title = QLabel("SPEED")
        self.speed_title.setObjectName("section")
        self.speed_label = QLabel("1.0x")
        speed_header.addWidget(self.speed_title)
        speed_header.addStretch()
        speed_header.addWidget(self.speed_label)
        effects_layout.addWidget(self.speed_header_widget)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(2, 40)
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(self._speed_changed)
        effects_layout.addWidget(self.speed_slider)

        self.music_panel = QWidget()
        music_layout = QVBoxLayout(self.music_panel)
        music_layout.setContentsMargins(0, 4, 0, 0)
        self.music_hint = QLabel("Audio source ready • sensitivity controls the lighting response")
        self.music_hint.setObjectName("hint")
        self.music_meter = QProgressBar()
        self.music_meter.setRange(0, 100)
        self.music_meter.setTextVisible(False)
        music_layout.addWidget(self.music_hint)
        music_layout.addWidget(self.music_meter)
        effects_layout.addWidget(self.music_panel)

        self.default_panel = QFrame()
        self.default_panel.setObjectName("notice")
        default_layout = QHBoxLayout(self.default_panel)
        default_layout.setContentsMargins(14, 9, 14, 9)
        default_icon = QLabel("◉")
        default_icon.setStyleSheet("color: #5ed1ff; font-size: 14px;")
        self.default_hint = QLabel(
            "BATTERY SAVER  •  normal bright backlight  •  sleeps after 10 seconds idle  •  wakes on any key"
        )
        self.default_hint.setObjectName("hint")
        default_layout.addWidget(default_icon)
        default_layout.addWidget(self.default_hint, 1)
        effects_layout.addWidget(self.default_panel)

        self.reactive_panel = QGroupBox("REACTIVE OPTIONS")
        reactive_layout = QVBoxLayout(self.reactive_panel)
        reaction_row = QHBoxLayout()
        reactions = [
            (1, "On → Off"), (2, "Dim → Bright"), (3, "Bright → Dim"),
            (4, "Off → Dim"), (5, "Off → Bright"),
        ]
        for value, label in reactions:
            button = QRadioButton(label)
            self.react_buttons.addButton(button, value)
            reaction_row.addWidget(button)
            if value == 1:
                button.setChecked(True)
        reactive_layout.addLayout(reaction_row)

        hold_row = QHBoxLayout()
        for value, label in [(1, "Blink repeatedly"), (2, "Stay active until released")]:
            button = QRadioButton(label)
            self.hold_buttons.addButton(button, value)
            hold_row.addWidget(button)
            if value == 1:
                button.setChecked(True)
        hold_row.addStretch()
        reactive_layout.addLayout(hold_row)
        self.react_buttons.buttonClicked.connect(self._restart_if_running)
        self.hold_buttons.buttonClicked.connect(self._restart_if_running)
        effects_layout.addWidget(self.reactive_panel)
        layout.addWidget(effects_panel)

        preferences = QHBoxLayout()
        preferences.setContentsMargins(4, 0, 4, 0)
        self.startup_checkbox = QCheckBox("RUN AT WINDOWS STARTUP")
        self.startup_checkbox.setChecked(startup_task_enabled())
        self.startup_checkbox.toggled.connect(self._set_startup)
        startup_note = QLabel("Appears in Task Manager Startup apps  •  launches elevated to the system tray")
        startup_note.setObjectName("hint")
        preferences.addWidget(self.startup_checkbox)
        preferences.addWidget(startup_note)
        preferences.addStretch()
        layout.addLayout(preferences)

        actions = QHBoxLayout()
        self.start_button = QPushButton("START MODE")
        self.start_button.setObjectName("start")
        self.start_button.clicked.connect(self.toggle_effect)
        light_button = QPushButton("LIGHT ON / OFF")
        light_button.clicked.connect(self.toggle_light)
        detect_button = QPushButton("RE-DETECT")
        detect_button.clicked.connect(self.redetect)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(light_button)
        actions.addWidget(detect_button)
        layout.addLayout(actions)
        footer = QLabel(f"THRASH  •  VERSION {APP_VERSION}  •  PRIVATE, LOCAL HARDWARE CONTROL")
        footer.setObjectName("hint")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        layout.addStretch(1)

    def selected_effect(self):
        button = self.effect_buttons.checkedButton()
        return button.property("effect_id") if button else None

    def showEvent(self, event):
        super().showEvent(event)
        if not self._has_animated:
            self._has_animated = True
            self.setWindowOpacity(0.0)
            self._entrance_animation = QPropertyAnimation(self, b"windowOpacity", self)
            self._entrance_animation.setDuration(520)
            self._entrance_animation.setStartValue(0.0)
            self._entrance_animation.setEndValue(1.0)
            self._entrance_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._entrance_animation.start()

    def _effect_changed(self, _button=None):
        effect = self.selected_effect()
        self.reactive_panel.setVisible(effect == "reactive")
        is_music = bool(effect and effect.startswith("music_"))
        self.music_panel.setVisible(is_music)
        is_default = effect == "default"
        self.default_panel.setVisible(is_default)
        self.speed_header_widget.setVisible(not is_default)
        self.speed_slider.setVisible(not is_default)
        self.speed_title.setText("SENSITIVITY" if is_music else "SPEED")
        if effect == "music_mic":
            self.music_hint.setText("DEFAULT MICROPHONE  •  follows nearby sound energy")
        elif effect == "music_speaker":
            self.music_hint.setText("BEAT DETECTION  •  adaptive output transients  •  no microphone recording")
        self._restart_if_running()

    def _speed_changed(self, value):
        speed = value / 10.0
        self.speed_label.setText(f"{speed:.1f}x")
        if self.engine.running:
            self.engine.speed = speed

    def _restart_if_running(self, _button=None):
        if self.engine.running:
            self.start_effect()

    def start_effect(self):
        if self.ctrl.method != "lenovo_vantage_dll":
            QMessageBox.warning(self, "Controller unavailable",
                                "A compatible Lenovo Vantage keyboard interface was not found.")
            return
        effect = self.selected_effect()
        try:
            self._shown_error = None
            self.engine.start(
                effect,
                self.speed_slider.value() / 10.0,
                self.react_buttons.checkedId(),
                self.hold_buttons.checkedId(),
            )
            effect_name = next(item["name"] for item in EffectEngine.EFFECTS_META if item["id"] == effect)
            self.state_label.setText(f"ACTIVE  /  {effect_name.upper()}")
            self.start_button.setText("STOP MODE")
            self.start_button.setProperty("running", True)
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
        except Exception as exc:
            QMessageBox.critical(self, "Could not start effect", str(exc))

    def stop_effect(self):
        self.engine.stop()
        self.state_label.setText("READY")
        self.start_button.setText("START MODE")
        self.start_button.setProperty("running", False)
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)

    def toggle_effect(self):
        self.stop_effect() if self.engine.running else self.start_effect()

    def _set_startup(self, enabled):
        try:
            set_startup_task(enabled)
            self.state_label.setText("STARTUP  /  ENABLED" if enabled else "STARTUP  /  DISABLED")
        except Exception as exc:
            self.startup_checkbox.blockSignals(True)
            self.startup_checkbox.setChecked(not enabled)
            self.startup_checkbox.blockSignals(False)
            QMessageBox.warning(self, "Startup setting failed", str(exc))

    def toggle_light(self):
        if self.engine.running:
            self.stop_effect()
        self.light_on = not self.light_on
        if self.ctrl.set_backlight(self.light_on):
            self.state_label.setText("LIGHT  /  ON" if self.light_on else "LIGHT  /  OFF")
        else:
            QMessageBox.warning(self, "Controller unavailable", "The keyboard command was not accepted.")

    def redetect(self):
        if self.engine.running:
            self.stop_effect()
        self.ctrl.detect_method()
        self._refresh_status()

    def _refresh_status(self):
        status = self.ctrl.get_status()
        self.method_label.setText(f"{status['system_model']}  •  {status['method_display']}")
        if status["method"] == "lenovo_vantage_dll":
            self.connection_dot.setStyleSheet("color: #2dd4bf;")
        elif status["method"] == "connecting":
            self.connection_dot.setStyleSheet("color: #fbbf24;")
        else:
            self.connection_dot.setStyleSheet("color: #fb7185;")
        self.music_meter.setValue(int(self.engine.music_level * 100))
        if self.engine.running and self.engine.current_effect == "default":
            if self.engine.idle_sleeping:
                self.state_label.setText("BATTERY SAVER  /  SLEEPING")
            else:
                remaining = max(0, 10 - int(self.engine.idle_seconds))
                self.state_label.setText(f"DEFAULT  /  IDLE SLEEP IN {remaining}s")
        if self.engine.last_error and self.engine.last_error != self._shown_error:
            self._shown_error = self.engine.last_error
            self.state_label.setText("Effect stopped")
            self.start_button.setText("START MODE")
            self.start_button.setProperty("running", False)
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
            QMessageBox.warning(self, "Effect stopped", self.engine.last_error)
        if not self.engine.running and (
            self.state_label.text().startswith("ACTIVE")
            or self.state_label.text().startswith("DEFAULT")
            or self.state_label.text().startswith("BATTERY SAVER")
        ):
            self.stop_effect()

    def closeEvent(self, event):
        if not self._quitting and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            if not self._tray_notice_shown:
                self._tray_notice_shown = True
                self.tray_icon.showMessage(
                    "Still running",
                    "Lenovo LOQ Backlit Effects is active in the system tray. Use the tray menu to quit.",
                    QSystemTrayIcon.Information,
                    3500,
                )
            return
        self._quit_application()
        event.accept()


class GodModeOverlay(QWidget):
    """Short, original red unlock sequence for the advanced-control reveal."""

    def __init__(self, parent):
        super().__init__(parent)
        self.progress = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def play(self, finished):
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(1150)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self._tick)
        self.animation.finished.connect(lambda: (self.hide(), finished()))
        self.animation.start()

    def _tick(self, value):
        self.progress = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pulse = math.sin(self.progress * math.pi)
        painter.fillRect(self.rect(), QColor(3, 2, 4, int(242 * pulse)))
        scan_x = int(self.width() * self.progress)
        glow = QLinearGradient(scan_x - 130, 0, scan_x + 35, 0)
        glow.setColorAt(0, QColor(255, 30, 55, 0))
        glow.setColorAt(0.72, QColor(255, 30, 55, int(90 * pulse)))
        glow.setColorAt(1, QColor(255, 87, 105, int(225 * pulse)))
        painter.fillRect(QRectF(scan_x - 130, 0, 165, self.height()), glow)
        painter.setPen(QPen(QColor(255, 64, 82, int(230 * pulse)), 2))
        painter.drawLine(scan_x, 0, scan_x, self.height())
        painter.setFont(QFont("Bahnschrift SemiCondensed", 10, QFont.DemiBold))
        painter.setPen(QColor(255, 100, 113, int(255 * pulse)))
        painter.drawText(QRectF(0, self.height() / 2 - 42, self.width(), 25),
                         Qt.AlignCenter, "ADVANCED LIGHTING CORE")
        painter.setFont(QFont("Bahnschrift SemiCondensed", 29, QFont.Bold))
        painter.setPen(QColor(255, 244, 246, int(255 * pulse)))
        message = "GOD MODE // ACTIVE" if self.progress > 0.62 else "UNLOCKING GOD MODE"
        painter.drawText(QRectF(0, self.height() / 2 - 15, self.width(), 62),
                         Qt.AlignCenter, message)
        painter.end()


# v3 replaces the original single-page shell above. Keeping the earlier class in
# this source preserves an easy migration reference while this definition is the
# one instantiated by the entry point.
class DesktopApplication(QMainWindow):
    """Legion-inspired, original desktop shell with progressive disclosure."""

    LIGHTING_IDS = {
        "battery_saver", "breathe", "heartbeat", "disco", "pulse",
        "binary", "wave", "reactive",
    }
    AUDIO_IDS = {"music_mic", "music_speaker"}

    def __init__(self, ctrl, effect_engine):
        super().__init__()
        self.ctrl = ctrl
        self.engine = effect_engine
        self.settings = QSettings("Thrash", "Lenovo LOQ Backlit Effects")
        self.god_mode = self.settings.value("godMode", False, type=bool)
        self.close_to_tray = self.settings.value("closeToTray", True, type=bool)
        self.animations_enabled = self.settings.value("animations", True, type=bool)
        self.intensity = max(1, min(self.settings.value("intensity", 50, type=int), 100))
        self.engine.idle_timeout = max(10, min(self.settings.value("idleTimeout", 30, type=int), 300))
        self.light_on = False
        self._shown_error = None
        self._quitting = False
        self._tray_notice_shown = False
        self._has_animated = False
        self.effect_buttons = QButtonGroup(self)
        self.nav_buttons = QButtonGroup(self)
        self.react_buttons = QButtonGroup(self)
        self.hold_buttons = QButtonGroup(self)
        self.advanced_widgets = []
        self.cards = {}
        self._build_ui()
        self._build_tray()
        self._apply_god_mode(repaint=True)
        self._select_effect("battery_saver")
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(250)
        self._refresh_status()

    def _build_ui(self):
        self.setWindowTitle("Lenovo LOQ Backlit Effects - Thrash")
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "app-icon.png"))))
        self.resize(1280, 820)
        self.setMinimumSize(1040, 700)
        self._set_theme()
        central = AmbientBackground()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)
        root.addWidget(self._make_sidebar())

        body = QVBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._make_header())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._scroll_page(self._lighting_page()))
        self.pages.addWidget(self._scroll_page(self._audio_page()))
        self.pages.addWidget(self._scroll_page(self._device_page()))
        self.pages.addWidget(self._scroll_page(self._settings_page()))
        self.pages.addWidget(self._scroll_page(self._about_page()))
        body.addWidget(self.pages, 1)
        body.addWidget(self._make_action_bar())
        root.addLayout(body, 1)
        self.god_overlay = GodModeOverlay(central)

    def _set_theme(self):
        accent = "#ff4055" if self.god_mode else "#42c8ff"
        accent_soft = "#451019" if self.god_mode else "#103c52"
        self.setStyleSheet(f"""
            QMainWindow {{ background: #05070c; }}
            QWidget {{ color: #eaf1f7; font: 9.5pt 'Segoe UI Variable Text'; }}
            QLabel {{ background: transparent; }}
            QLabel#title {{ font: 700 25pt 'Bahnschrift SemiCondensed'; color: #fbfdff; }}
            QLabel#pageTitle {{ font: 650 20pt 'Bahnschrift SemiCondensed'; color: #f7fbff; }}
            QLabel#section {{ color: {accent}; font: 650 8pt 'Bahnschrift SemiCondensed'; }}
            QLabel#muted {{ color: #8fa2b5; }}
            QLabel#brand {{ color: #ffffff; font: 700 13pt 'Bahnschrift SemiCondensed'; }}
            QLabel#brandSlash {{ color: {accent}; font: 900 18pt 'Bahnschrift SemiCondensed'; }}
            QFrame#sidebar, QFrame#glass, QGroupBox {{ background: rgba(8, 14, 24, 224);
                border: 1px solid rgba(113, 151, 184, 62); border-radius: 18px; }}
            QFrame#sidebar {{ background: rgba(4, 8, 14, 239); }}
            QFrame#status {{ background: rgba(8, 15, 25, 214); border: 1px solid rgba(95, 142, 174, 65); border-radius: 13px; }}
            QPushButton {{ background: rgba(24, 35, 50, 238); border: 1px solid rgba(105, 141, 175, 55);
                border-radius: 11px; padding: 10px 15px; font: 600 9pt 'Segoe UI Variable Text'; }}
            QPushButton:hover {{ border-color: {accent}; background: rgba(34, 49, 68, 245); }}
            QPushButton#nav {{ text-align: left; background: transparent; border: 0; padding: 13px 15px; color: #8fa2b6; }}
            QPushButton#nav:checked {{ color: #ffffff; background: {accent_soft}; border-left: 3px solid {accent}; }}
            QPushButton#primary {{ background: {accent}; color: #05080d; border: 0; font-weight: 750; }}
            QPushButton#primary[running='true'] {{ background: #ff5367; color: #160407; }}
            QCheckBox {{ spacing: 10px; padding: 6px; color: #c7d3de; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid #536b82; border-radius: 6px; background: #0a121e; }}
            QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
            QRadioButton {{ padding: 6px; color: #c8d5df; }}
            QGroupBox {{ margin-top: 12px; padding: 16px 12px 12px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 14px; color: {accent}; padding: 0 6px; }}
            QSlider::groove:horizontal {{ height: 6px; background: #233248; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ width: 19px; margin: -7px 0; background: #eaf8ff; border: 2px solid {accent}; border-radius: 9px; }}
            QProgressBar {{ height: 8px; background: #1e2a3c; border: 0; border-radius: 4px; }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
            QScrollArea {{ border: 0; background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """)

    def _make_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(206)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 18)
        logo = QHBoxLayout()
        slash = QLabel("T//")
        slash.setObjectName("brandSlash")
        word = QLabel("THRASH")
        word.setObjectName("brand")
        logo.addWidget(slash)
        logo.addWidget(word)
        logo.addStretch()
        layout.addLayout(logo)
        edition = QLabel("LOQ LIGHTING LAB")
        edition.setObjectName("muted")
        layout.addWidget(edition)
        layout.addSpacing(24)
        for index, (icon, text) in enumerate([
            ("◈", "Lighting"), ("♫", "Audio Reactive"), ("▣", "Device"),
            ("⚙", "Settings"), ("ⓘ", "About"),
        ]):
            button = QPushButton(f"{icon}    {text}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.pages.setCurrentIndex(i))
            self.nav_buttons.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        layout.addStretch()
        self.god_badge = QLabel("GOD MODE  //  ARMED")
        self.god_badge.setAlignment(Qt.AlignCenter)
        self.god_badge.setStyleSheet("color:#ff6879; border:1px solid #8f2633; border-radius:10px; padding:8px; font-weight:700;")
        layout.addWidget(self.god_badge)
        return sidebar

    def _make_header(self):
        panel = QFrame()
        panel.setObjectName("status")
        row = QHBoxLayout(panel)
        row.setContentsMargins(18, 13, 18, 13)
        titles = QVBoxLayout()
        title = QLabel("LENOVO LOQ BACKLIT EFFECTS")
        title.setObjectName("title")
        subtitle = QLabel("Native white-backlight control  •  private and local")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        self.connection_dot = QLabel("●")
        self.connection_dot.setStyleSheet("color:#2dd4bf; font-size:15px;")
        self.method_label = QLabel("Detecting Lenovo lighting bridge…")
        self.state_label = QLabel("READY")
        self.state_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addLayout(titles, 1)
        row.addWidget(self.connection_dot)
        row.addWidget(self.method_label)
        row.addSpacing(16)
        row.addWidget(self.state_label)
        return panel

    def _scroll_page(self, content):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _page(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        note = QLabel(subtitle)
        note.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(note)
        return page, layout

    def _card_grid(self, ids, columns=3):
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        effects = [item for item in EffectEngine.EFFECTS_META if item["id"] in ids]
        for index, effect in enumerate(effects):
            card = EffectCard(effect)
            card.setProperty("effect_id", effect["id"])
            self.effect_buttons.addButton(card)
            self.cards[effect["id"]] = card
            card.clicked.connect(self._effect_changed)
            grid.addWidget(card, index // columns, index % columns)
        return host

    def _lighting_page(self):
        page, layout = self._page("LIGHTING", "Curated effects with hardware-safe automatic timing.")
        layout.addWidget(self._card_grid(self.LIGHTING_IDS, 3))
        self.battery_note = QLabel("BATTERY SAVER  •  softly wakes to your chosen intensity  •  sleeps after 30 seconds")
        self.battery_note.setObjectName("muted")
        layout.addWidget(self.battery_note)
        self.advanced_panel = QGroupBox("GOD MODE  /  ADVANCED TIMING")
        advanced = QVBoxLayout(self.advanced_panel)
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("EFFECT SPEED"))
        speed_row.addStretch()
        self.speed_label = QLabel("1.0×")
        speed_row.addWidget(self.speed_label)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(2, 40)
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(self._speed_changed)
        advanced.addLayout(speed_row)
        advanced.addWidget(self.speed_slider)
        self.reactive_options = QGroupBox("REACTIVE LAB")
        react_layout = QVBoxLayout(self.reactive_options)
        reaction_row = QHBoxLayout()
        for value, text_value in [(1, "On → Off"), (2, "Dim → Bright"), (3, "Bright → Dim"), (4, "Off → Dim"), (5, "Off → Bright")]:
            option = QRadioButton(text_value)
            self.react_buttons.addButton(option, value)
            reaction_row.addWidget(option)
            if value == 2:
                option.setChecked(True)
        react_layout.addLayout(reaction_row)
        hold_row = QHBoxLayout()
        for value, text_value in [(1, "Pulse once"), (2, "Stay bright while held")]:
            option = QRadioButton(text_value)
            self.hold_buttons.addButton(option, value)
            hold_row.addWidget(option)
            if value == 2:
                option.setChecked(True)
        hold_row.addStretch()
        react_layout.addLayout(hold_row)
        advanced.addWidget(self.reactive_options)
        layout.addWidget(self.advanced_panel)
        self.advanced_widgets.extend([self.advanced_panel])
        layout.addStretch()
        return page

    def _audio_page(self):
        page, layout = self._page("AUDIO REACTIVE", "Two local audio paths: microphone energy or Windows speaker beats.")
        layout.addWidget(self._card_grid(self.AUDIO_IDS, 2))
        audio = QFrame()
        audio.setObjectName("glass")
        audio_layout = QVBoxLayout(audio)
        self.audio_source_label = QLabel("SPEAKER MODE listens to Windows output—not the microphone.")
        self.audio_source_label.setObjectName("muted")
        self.music_meter = QProgressBar()
        self.music_meter.setRange(0, 100)
        self.music_meter.setTextVisible(False)
        audio_layout.addWidget(self.audio_source_label)
        audio_layout.addWidget(self.music_meter)
        layout.addWidget(audio)
        layout.addStretch()
        return page

    def _device_page(self):
        page, layout = self._page("DEVICE", "Capability-first detection for Lenovo LOQ white-backlit keyboards.")
        panel = QFrame()
        panel.setObjectName("glass")
        info = QGridLayout(panel)
        self.device_values = {}
        for row, (key, title) in enumerate([("model", "SYSTEM"), ("capability", "BACKLIGHT"), ("native", "NATIVE LEVEL"), ("contract", "VANTAGE CONTRACT")]):
            label = QLabel(title)
            label.setObjectName("section")
            value = QLabel("Detecting…")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.device_values[key] = value
            info.addWidget(label, row, 0)
            info.addWidget(value, row, 1)
        layout.addWidget(panel)
        buttons = QHBoxLayout()
        redetect = QPushButton("RE-DETECT HARDWARE")
        redetect.clicked.connect(self.redetect)
        copy = QPushButton("COPY DIAGNOSTICS")
        copy.clicked.connect(self._copy_diagnostics)
        buttons.addWidget(redetect)
        buttons.addWidget(copy)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _settings_page(self):
        page, layout = self._page("SETTINGS", "Simple by default. Experimental controls unlock only when requested.")
        panel = QFrame()
        panel.setObjectName("glass")
        settings_layout = QVBoxLayout(panel)
        self.startup_checkbox = QCheckBox("RUN AT WINDOWS STARTUP (VISIBLE IN TASK MANAGER)")
        self.startup_checkbox.setChecked(startup_task_enabled())
        self.startup_checkbox.toggled.connect(self._set_startup)
        self.tray_checkbox = QCheckBox("KEEP RUNNING IN THE SYSTEM TRAY WHEN CLOSED")
        self.tray_checkbox.setChecked(self.close_to_tray)
        self.tray_checkbox.toggled.connect(self._set_close_to_tray)
        self.animation_checkbox = QCheckBox("ENABLE INTERFACE ANIMATIONS")
        self.animation_checkbox.setChecked(self.animations_enabled)
        self.animation_checkbox.toggled.connect(self._set_animations)
        self.god_checkbox = QCheckBox("ENABLE GOD MODE — ADVANCED LIGHTING CONTROLS")
        self.god_checkbox.setChecked(self.god_mode)
        self.god_checkbox.toggled.connect(self._toggle_god_mode)
        for widget in [self.startup_checkbox, self.tray_checkbox, self.animation_checkbox, self.god_checkbox]:
            settings_layout.addWidget(widget)
        warning = QLabel("God Mode changes lighting timing only. It does not overclock the CPU, GPU, or keyboard hardware.")
        warning.setObjectName("muted")
        settings_layout.addWidget(warning)
        layout.addWidget(panel)
        self.god_settings = QGroupBox("GOD MODE  /  BATTERY SAVER LAB")
        god_layout = QVBoxLayout(self.god_settings)
        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("IDLE TIMEOUT"))
        timeout_row.addStretch()
        self.timeout_label = QLabel(f"{int(self.engine.idle_timeout)} SEC")
        timeout_row.addWidget(self.timeout_label)
        self.timeout_slider = QSlider(Qt.Horizontal)
        self.timeout_slider.setRange(10, 300)
        self.timeout_slider.setValue(int(self.engine.idle_timeout))
        self.timeout_slider.valueChanged.connect(self._timeout_changed)
        god_layout.addLayout(timeout_row)
        god_layout.addWidget(self.timeout_slider)
        layout.addWidget(self.god_settings)
        self.advanced_widgets.append(self.god_settings)
        reset = QPushButton("RESET INTERFACE DEFAULTS")
        reset.clicked.connect(self._reset_defaults)
        layout.addWidget(reset, 0, Qt.AlignLeft)
        layout.addStretch()
        return page

    def _about_page(self):
        page, layout = self._page("ABOUT", f"Lenovo LOQ Backlit Effects - Thrash  •  Version {APP_VERSION}")
        panel = QFrame()
        panel.setObjectName("glass")
        box = QVBoxLayout(panel)
        title = QLabel("T//  THRASH LIGHTING LAB")
        title.setObjectName("title")
        body = QLabel(
            "A community-built controller for compatible Lenovo LOQ white-backlit keyboards.\n\n"
            "Privacy: lighting, keyboard activity, and audio analysis remain on this PC. No recordings or telemetry are uploaded.\n\n"
            "Compatibility: Lenovo Vantage must expose the supported white-backlight contract. RGB models are intentionally excluded.\n\n"
            "Lenovo, LOQ, Legion, ASUS, TUF, and Armoury Crate are trademarks of their respective owners. This project is independent and unaffiliated."
        )
        body.setWordWrap(True)
        body.setObjectName("muted")
        credits = QLabel("© 2026 THRASH. OPEN-SOURCE COMMUNITY SOFTWARE.")
        credits.setObjectName("section")
        box.addWidget(title)
        box.addWidget(body)
        box.addSpacing(12)
        box.addWidget(credits)
        layout.addWidget(panel)
        layout.addStretch()
        return page

    def _make_action_bar(self):
        panel = QFrame()
        panel.setObjectName("glass")
        row = QHBoxLayout(panel)
        row.setContentsMargins(15, 11, 15, 11)
        row.addWidget(QLabel("INTENSITY"))
        self.intensity_slider = QSlider(Qt.Horizontal)
        self.intensity_slider.setRange(1, 100)
        self.intensity_slider.setValue(self.intensity)
        self.intensity_slider.valueChanged.connect(self._intensity_changed)
        self.intensity_value = QLabel(f"{self.intensity}%")
        self.intensity_value.setFixedWidth(45)
        self.start_button = QPushButton("START MODE")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle_effect)
        light = QPushButton("LIGHT ON / OFF")
        light.clicked.connect(self.toggle_light)
        row.addWidget(self.intensity_slider, 1)
        row.addWidget(self.intensity_value)
        row.addSpacing(8)
        row.addWidget(self.start_button)
        row.addWidget(light)
        return panel

    def _build_tray(self):
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip("Lenovo LOQ Backlit Effects - Thrash")
        menu = QMenu()
        open_action = QAction("Open Lighting Lab", self)
        open_action.triggered.connect(self._restore_from_tray)
        battery_action = QAction("Arm Battery Saver", self)
        battery_action.triggered.connect(self.arm_startup_battery_saver)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_application)
        menu.addAction(open_action)
        menu.addAction(battery_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _select_effect(self, effect_id):
        card = self.cards.get(effect_id)
        if card:
            card.setChecked(True)
            self._effect_changed()

    def selected_effect(self):
        button = self.effect_buttons.checkedButton()
        return button.property("effect_id") if button else "battery_saver"

    def _effect_changed(self, _checked=False):
        effect = self.selected_effect()
        self.reactive_options.setVisible(self.god_mode and effect == "reactive")
        self.advanced_panel.setVisible(self.god_mode)
        self.audio_source_label.setText(
            "MIC MODE follows the default microphone locally."
            if effect == "music_mic" else
            "SPEAKER MODE uses Windows loopback output and adaptive beat transients—not the microphone."
        )

    def _speed_changed(self, value):
        self.speed_label.setText(f"{value / 10:.1f}×")
        if self.god_mode and self.engine.running:
            self.engine.speed = value / 10

    def _intensity_changed(self, value):
        self.intensity = value
        self.intensity_value.setText(f"{value}%")
        self.settings.setValue("intensity", value)
        if self.engine.running:
            self.engine.intensity = value

    def _timeout_changed(self, value):
        self.engine.idle_timeout = float(value)
        self.timeout_label.setText(f"{value} SEC")
        self.battery_note.setText(f"BATTERY SAVER  •  softly wakes to your chosen intensity  •  sleeps after {value} seconds")
        self.settings.setValue("idleTimeout", value)

    def _toggle_god_mode(self, enabled):
        self.god_mode = bool(enabled)
        self.settings.setValue("godMode", self.god_mode)
        if enabled and self.animations_enabled:
            for widget in self.advanced_widgets:
                widget.hide()
            self.god_overlay.play(lambda: self._apply_god_mode(repaint=True))
        else:
            self._apply_god_mode(repaint=True)

    def _apply_god_mode(self, repaint=False):
        for widget in self.advanced_widgets:
            widget.setVisible(self.god_mode)
        self.god_badge.setVisible(self.god_mode)
        if hasattr(self, "reactive_options"):
            self.reactive_options.setVisible(self.god_mode and self.selected_effect() == "reactive")
        if repaint:
            self._set_theme()
            for card in self.cards.values():
                card.update()

    def _set_close_to_tray(self, enabled):
        self.close_to_tray = bool(enabled)
        self.settings.setValue("closeToTray", self.close_to_tray)

    def _set_animations(self, enabled):
        self.animations_enabled = bool(enabled)
        self.settings.setValue("animations", self.animations_enabled)

    def _reset_defaults(self):
        self.god_checkbox.setChecked(False)
        self.tray_checkbox.setChecked(True)
        self.animation_checkbox.setChecked(True)
        self.intensity_slider.setValue(50)
        self.timeout_slider.setValue(30)
        self.speed_slider.setValue(10)
        self.react_buttons.button(2).setChecked(True)
        self.hold_buttons.button(2).setChecked(True)
        self.state_label.setText("DEFAULTS RESTORED")

    def start_effect(self, start_asleep=False):
        if self.ctrl.method != "lenovo_vantage_dll":
            QMessageBox.warning(self, "Controller unavailable", "A compatible Lenovo white-backlight interface was not found.")
            return False
        effect = self.selected_effect()
        try:
            speed = self.speed_slider.value() / 10 if self.god_mode else None
            mode = self.react_buttons.checkedId() if self.god_mode else 2
            hold = self.hold_buttons.checkedId() if self.god_mode else 2
            self.engine.start(effect, intensity=self.intensity, speed=speed, mode=mode,
                              hold_behavior=hold, start_asleep=start_asleep)
            name = next(item["name"] for item in EffectEngine.EFFECTS_META if item["id"] == effect)
            self.state_label.setText(f"ACTIVE  /  {name.upper()}")
            self.start_button.setText("STOP MODE")
            self.start_button.setProperty("running", True)
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Could not start effect", str(exc))
            return False

    def arm_startup_battery_saver(self):
        self._select_effect("battery_saver")
        self.ctrl.set_brightness(0)
        self.light_on = False
        self.start_effect(start_asleep=True)

    def stop_effect(self):
        self.engine.stop()
        self.state_label.setText("READY")
        self.start_button.setText("START MODE")
        self.start_button.setProperty("running", False)
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)

    def toggle_effect(self):
        self.stop_effect() if self.engine.running else self.start_effect()

    def toggle_light(self):
        if self.engine.running:
            self.stop_effect()
        self.light_on = not self.light_on
        target = max(1, int(round((self.intensity / 100.0) * self.ctrl.max_level))) if self.light_on else 0
        target = min(self.ctrl.max_level, target)
        if self.ctrl.set_brightness(target):
            self.state_label.setText("LIGHT  /  ON" if self.light_on else "LIGHT  /  OFF")
        else:
            QMessageBox.warning(self, "Controller unavailable", "The keyboard command was not accepted.")

    def redetect(self):
        if self.engine.running:
            self.stop_effect()
        self.ctrl.detect_method()
        self._refresh_status()

    def _copy_diagnostics(self):
        status = self.ctrl.get_status()
        lines = [
            f"Lenovo LOQ Backlit Effects - Thrash {APP_VERSION}",
            f"System: {status.get('system_model', 'Unknown')}",
            f"Bridge: {status.get('method_display', 'Unknown')}",
            f"Capability: {status.get('backlight_level_type', 'Unknown')}",
            f"Native level: {status.get('current_level', 'Unknown')} / {status.get('max_level', 'Unknown')}",
            f"Contract: {status.get('contract_version', 'Unknown')}",
            f"Administrator: {status.get('is_admin', False)}",
            f"Last error: {status.get('last_error') or 'None'}",
        ]
        QApplication.clipboard().setText("\n".join(lines))
        self.state_label.setText("DIAGNOSTICS COPIED")

    def _set_startup(self, enabled):
        try:
            set_startup_task(enabled)
            self.state_label.setText("STARTUP  /  ENABLED" if enabled else "STARTUP  /  DISABLED")
        except Exception as exc:
            self.startup_checkbox.blockSignals(True)
            self.startup_checkbox.setChecked(not enabled)
            self.startup_checkbox.blockSignals(False)
            QMessageBox.warning(self, "Startup setting failed", str(exc))

    def _refresh_status(self):
        status = self.ctrl.get_status()
        self.method_label.setText(f"{status.get('system_model', 'Lenovo LOQ')}  •  {status.get('method_display', 'Unknown')}")
        method = status.get("method")
        self.connection_dot.setStyleSheet(
            "color:#2dd4bf; font-size:15px;" if method == "lenovo_vantage_dll" else
            "color:#fbbf24; font-size:15px;" if method == "connecting" else
            "color:#fb7185; font-size:15px;"
        )
        self.music_meter.setValue(int(self.engine.music_level * 100))
        self.device_values["model"].setText(status.get("system_model", "Unknown"))
        capability = status.get("backlight_level_type", "Unknown")
        if status.get("compatible_white_backlight"):
            capability += "  •  compatible white backlight"
        self.device_values["capability"].setText(capability)
        self.device_values["native"].setText(f"{status.get('current_level', 0)} of {status.get('max_level', 2)}")
        self.device_values["contract"].setText(status.get("contract_version", "Unknown"))
        if self.engine.running and self.engine.current_effect == "battery_saver":
            if self.intensity != self.engine.intensity:
                self.intensity = self.engine.intensity
                self.intensity_slider.blockSignals(True)
                self.intensity_slider.setValue(self.intensity)
                self.intensity_slider.blockSignals(False)
                self.intensity_value.setText(f"{self.intensity}%")
                self.settings.setValue("intensity", self.intensity)
            if self.engine.idle_sleeping:
                self.state_label.setText("BATTERY SAVER  /  SLEEPING")
            else:
                remaining = max(0, int(math.ceil(self.engine.idle_timeout - self.engine.idle_seconds)))
                self.state_label.setText(f"BATTERY SAVER  /  SLEEP IN {remaining}s")
        if self.engine.last_error and self.engine.last_error != self._shown_error:
            self._shown_error = self.engine.last_error
            QMessageBox.warning(self, "Effect stopped", self.engine.last_error)
        if not self.engine.running and self.start_button.property("running"):
            self.start_button.setText("START MODE")
            self.start_button.setProperty("running", False)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._has_animated and self.animations_enabled:
            self._has_animated = True
            self.setWindowOpacity(0.0)
            self._entrance_animation = QPropertyAnimation(self, b"windowOpacity", self)
            self._entrance_animation.setDuration(480)
            self._entrance_animation.setStartValue(0.0)
            self._entrance_animation.setEndValue(1.0)
            self._entrance_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._entrance_animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "god_overlay"):
            self.god_overlay.setGeometry(self.centralWidget().rect())

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_application(self):
        self._quitting = True
        self.status_timer.stop()
        self.engine.stop()
        self.ctrl.shutdown()
        self.tray_icon.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if not self._quitting and self.close_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            if not self._tray_notice_shown:
                self._tray_notice_shown = True
                self.tray_icon.showMessage("Still running", "Lighting control continues in the system tray.", QSystemTrayIcon.Information, 3200)
            return
        self._quit_application()
        event.accept()

# ---------------------------------------------------------------------------
#  Shutdown Hook
# ---------------------------------------------------------------------------

import atexit
@atexit.register
def cleanup():
    if engine is not None:
        engine.stop()
    if controller is not None:
        controller.shutdown()

# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    startup_launch = "--startup" in sys.argv

    # The packaged EXE is built with a requireAdministrator manifest. When
    # running from source, still provide a friendly UAC elevation fallback.
    if not is_admin():
        try:
            args = list(sys.argv[1:])
            if not getattr(sys, "frozen", False):
                args.insert(0, os.path.abspath(sys.argv[0]))
            params = " ".join(f'"{arg}"' for arg in args)
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            if result <= 32:
                raise RuntimeError(f"ShellExecuteW failed with code {result}")
            sys.exit(0)
        except Exception as exc:
            print(f"Administrator privileges are required: {exc}")
            sys.exit(1)

    if startup_launch:
        sys.argv.remove("--startup")

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Lenovo LOQ Backlit Effects - Thrash")
    qt_app.setApplicationDisplayName("Lenovo LOQ Backlit Effects - Thrash")
    qt_app.setApplicationVersion(APP_VERSION)
    qt_app.setOrganizationName("Thrash")
    qt_app.setWindowIcon(QIcon(resource_path(os.path.join("assets", "app-icon.png"))))
    qt_app.setFont(QFont("Segoe UI Variable Text", 10))
    qt_app.setQuitOnLastWindowClosed(False)

    splash = BootSplash()
    if startup_launch:
        splash.started -= 2.4
    else:
        splash.show()
    bootstrap = {}

    def initialize_hardware():
        try:
            bootstrap["controller"] = KeyboardBacklightController()
            bootstrap["engine"] = EffectEngine(bootstrap["controller"])
        except Exception as exc:
            bootstrap["error"] = exc

    threading.Thread(target=initialize_hardware, daemon=True).start()
    boot_timer = QTimer()

    def finish_boot():
        global controller, engine, window
        if time.monotonic() - splash.started < 2.4:
            return
        if "error" in bootstrap:
            boot_timer.stop()
            splash.close()
            QMessageBox.critical(None, "Startup failed", str(bootstrap["error"]))
            qt_app.quit()
            return
        if "controller" not in bootstrap:
            return
        boot_timer.stop()
        controller = bootstrap["controller"]
        engine = bootstrap["engine"]
        window = DesktopApplication(controller, engine)
        if startup_launch:
            window.arm_startup_battery_saver()
        else:
            window.show()
        splash.close()

    boot_timer.timeout.connect(finish_boot)
    boot_timer.start(45)
    sys.exit(qt_app.exec())
