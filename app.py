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
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter,
    QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QCheckBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QRadioButton,
    QProgressBar, QSizePolicy, QSlider, QVBoxLayout, QWidget,
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


STARTUP_TASK_NAME = "Lenovo LOQ Backlit Effects - Thrash"


def _hidden_process_kwargs():
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def startup_task_enabled():
    """Return whether the per-user Windows logon task exists."""
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


def set_startup_task(enabled):
    """Create or remove the elevated per-user Windows logon task."""
    if enabled:
        if getattr(sys, "frozen", False):
            target = f'"{sys.executable}"'
        else:
            target = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        command = [
            "schtasks", "/Create", "/TN", STARTUP_TASK_NAME,
            "/TR", target, "/SC", "ONLOGON", "/RL", "HIGHEST", "/F",
        ]
    else:
        command = ["schtasks", "/Delete", "/TN", STARTUP_TASK_NAME, "/F"]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **_hidden_process_kwargs(),
    )
    if result.returncode != 0 and not (not enabled and result.returncode == 1):
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
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
            model = winreg.QueryValueEx(key, "SystemProductName")[0]
            winreg.CloseKey(key)
            return model.strip()
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
                """
                self.ps_proc.stdin.write(init_script + "\n")
                self.ps_proc.stdin.flush()

                if not self._send_command("Level_2"):
                    raise RuntimeError("Lenovo Vantage rejected the keyboard backlight command")
                self.method = "lenovo_vantage_dll"
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"Error initializing Vantage DLL control: {e}")
                self.close_ps()
        else:
            self.last_error = "Lenovo Vantage keyboard DLLs were not found"

        self.method = "unavailable"
        return False

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
        {"id": "default",   "name": "Default Backlight", "icon": "◉",  "desc": "Normal light with 10-second idle sleep"},
        {"id": "blink",     "name": "Blink",          "icon": "●",     "desc": "Classic on-and-off blinking"},
        {"id": "breathe",   "name": "Breathe",        "icon": "◌",     "desc": "Smooth fade in and out"},
        {"id": "strobe",    "name": "Strobe",         "icon": "ϟ",     "desc": "Rapid strobe flashing"},
        {"id": "heartbeat", "name": "Heartbeat",      "icon": "♥",     "desc": "Double-pulse heartbeat rhythm"},
        {"id": "sos",       "name": "SOS",            "icon": "···",   "desc": "Morse code emergency signal"},
        {"id": "disco",     "name": "Disco",          "icon": "✦",     "desc": "Random high-energy flashing"},
        {"id": "lightning", "name": "Lightning",      "icon": "↯",     "desc": "Random lightning strikes"},
        {"id": "pulse",     "name": "Pulse",          "icon": "◍",     "desc": "Quick flash with a slow fade"},
        {"id": "candle",    "name": "Candle",         "icon": "♨",     "desc": "Warm flickering rhythm"},
        {"id": "binary",    "name": "Binary Clock",   "icon": "01",    "desc": "Encodes seconds in binary"},
        {"id": "wave",      "name": "Wave",           "icon": "≈",     "desc": "Rolling brightness crest"},
        {"id": "reactive",  "name": "Reactive",       "icon": "⌨",     "desc": "Responds instantly to typing"},
        {"id": "music_mic", "name": "Music / Mic",    "icon": "♪",     "desc": "Follows the default microphone"},
        {"id": "music_speaker", "name": "Music / Speaker", "icon": "♫", "desc": "Beat detection from speaker output"},
    ]

    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.running = False
        self.current_effect = None
        self.speed = 1.0
        self.mode = 1
        self.hold_behavior = 1 # 1 = Constant blink, 2 = Stay active until held key released
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
        self.idle_sleeping = False
        self.idle_seconds = 0.0
        self.music_level = 0.0
        self.last_error = None

    def start(self, effect, speed=1.0, mode=1, hold_behavior=1):
        valid_effects = {item["id"] for item in self.EFFECTS_META}
        if effect not in valid_effects:
            raise ValueError(f"Unknown effect: {effect}")
        self.stop()
        self.current_effect = effect
        self.speed = max(0.1, min(speed, 5.0))
        self.mode = mode
        self.hold_behavior = hold_behavior
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
        self.idle_sleeping = False
        self.idle_seconds = 0.0
        self.music_level = 0.0
        with self._keys_lock:
            self._pressed_keys.clear()
        self.running = True
        self._stop.clear()

        # Reactive and battery-saving default modes both need global input.
        if self.current_effect in ("reactive", "default"):
            self._start_keyboard_hook()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop.set()

        # Terminate keyboard hook if active
        self._stop_keyboard_hook()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._close_music_stream()
        self.ctrl.set_backlight(True)
        self.current_effect = None

    def _wait(self, secs):
        self._stop.wait(secs)
        return not self.running

    def _loop(self):
        fns = {
            "default": self._default_backlight,
            "blink": self._blink, "breathe": self._breathe,
            "strobe": self._strobe, "heartbeat": self._heartbeat,
            "sos": self._sos, "disco": self._disco,
            "lightning": self._lightning, "pulse": self._pulse,
            "candle": self._candle, "binary": self._binary,
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
            self.ctrl.set_backlight(True)

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

    def _default_backlight(self):
        """Keep normal backlight on, sleep after 10 idle seconds, wake on input."""
        if self._keypress_event.is_set():
            self._keypress_event.clear()
            self._idle_started = time.monotonic()
            self.idle_seconds = 0.0
            if self.idle_sleeping:
                self.idle_sleeping = False

        self.idle_seconds = max(0.0, time.monotonic() - self._idle_started)
        if self.idle_seconds >= 10.0 and not self.idle_sleeping:
            self.idle_sleeping = True
        desired_level = 0 if self.idle_sleeping else 2
        if desired_level != self._default_level:
            self.ctrl.set_brightness(desired_level)
            self._default_level = desired_level
        return self._wait(0.1)

    def _blink(self):
        d = 0.5 / self.speed
        self.ctrl.set_backlight(True)
        if self._wait(d): return True
        self.ctrl.set_backlight(False)
        if self._wait(d): return True

    def _breathe(self):
        d = 0.35 / self.speed
        self.ctrl.set_brightness(0)
        if self._wait(d): return True
        self.ctrl.set_brightness(1)
        if self._wait(d): return True
        self.ctrl.set_brightness(2)
        if self._wait(d * 1.5): return True
        self.ctrl.set_brightness(1)
        if self._wait(d): return True

    def _strobe(self):
        d = 0.08 / self.speed
        self.ctrl.set_backlight(True)
        if self._wait(d): return True
        self.ctrl.set_backlight(False)
        if self._wait(d): return True

    def _heartbeat(self):
        b, p, r = 0.12 / self.speed, 0.15 / self.speed, 0.7 / self.speed
        self.ctrl.set_brightness(2)
        if self._wait(b): return True
        self.ctrl.set_brightness(0)
        if self._wait(p): return True
        self.ctrl.set_brightness(2)
        if self._wait(b): return True
        self.ctrl.set_brightness(0)
        if self._wait(r): return True

    def _sos(self):
        dot, dash = 0.15 / self.speed, 0.45 / self.speed
        gap, lgap, wgap = 0.15 / self.speed, 0.45 / self.speed, 1.0 / self.speed
        def send(durs):
            for d in durs:
                self.ctrl.set_backlight(True)
                if self._wait(d): return True
                self.ctrl.set_backlight(False)
                if self._wait(gap): return True
            return False
        if send([dot]*3): return True
        if self._wait(lgap): return True
        if send([dash]*3): return True
        if self._wait(lgap): return True
        if send([dot]*3): return True
        if self._wait(wgap): return True

    def _disco(self):
        self.ctrl.set_backlight(True)
        if self._wait(random.uniform(0.04, 0.25) / self.speed): return True
        self.ctrl.set_backlight(False)
        if self._wait(random.uniform(0.04, 0.25) / self.speed): return True

    def _lightning(self):
        self.ctrl.set_backlight(False)
        if self._wait(random.uniform(0.4, 1.8) / self.speed): return True
        for _ in range(random.randint(1, 3)):
            self.ctrl.set_backlight(True)
            if self._wait(random.uniform(0.03, 0.1) / self.speed): return True
            self.ctrl.set_backlight(False)
            if self._wait(random.uniform(0.04, 0.12) / self.speed): return True

    def _pulse(self):
        self.ctrl.set_brightness(2)
        if self._wait(0.1 / self.speed): return True
        self.ctrl.set_brightness(1)
        if self._wait(0.15 / self.speed): return True
        self.ctrl.set_brightness(0)
        if self._wait(0.5 / self.speed): return True

    def _candle(self):
        self.ctrl.set_backlight(random.random() < 0.75)
        if self._wait(random.uniform(0.05, 0.2) / self.speed): return True

    def _binary(self):
        bits = format(datetime.datetime.now().second, "06b")
        for b in bits:
            if not self.running: return True
            self.ctrl.set_backlight(b == "1")
            if self._wait(0.35 / self.speed): return True
        self.ctrl.set_backlight(False)
        if self._wait(0.6 / self.speed): return True

    def _wave(self):
        """A rolling crest for single-zone keyboards: off -> dim -> bright -> dim."""
        step = 0.14 / self.speed
        for level, duration in [(0, step), (1, step), (2, step * 1.25), (1, step), (0, step * 1.8)]:
            self.ctrl.set_brightness(level)
            if self._wait(duration):
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
            level = 2
            target_meter = 1.0
        elif now < self._speaker_glow_until:
            level = 1
            target_meter = 0.48
        else:
            level = 0
            target_meter = min(0.28, raw_level * 1.8)

        self.music_level = self.music_level * 0.34 + target_meter * 0.66
        self.ctrl.set_brightness(level)
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

        if self.music_level >= 0.68:
            level = 2
        elif self.music_level >= 0.24:
            level = 1
        else:
            level = 0
        self.ctrl.set_brightness(level)

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
        """Keyboard lights react to keypresses based on the selected mode."""
        m = str(self.mode)
        if m == "2":
            base, active = 1, 2
        elif m == "3":
            base, active = 2, 1
        elif m == "4":
            base, active = 0, 1
        elif m == "5":
            base, active = 0, 2
        else: # Default/Mode 1
            base, active = 2, 0

        self.ctrl.set_brightness(base)
        self._keypress_event.clear()
        self._keyrelease_event.clear()

        # Block until a key is pressed (with a timeout so we check running state periodically)
        if self._keypress_event.wait(timeout=0.2):
            # Reaction
            self.ctrl.set_brightness(active)

            if str(self.hold_behavior) == "2":
                # Solid Hold: Stay active as long as any keys are pressed
                min_dur = 0.10 / self.speed
                self._wait(min_dur)

                with self._keys_lock:
                    keys_held = len(self._pressed_keys) > 0

                while keys_held and self.running:
                    self._keyrelease_event.wait(timeout=0.2)
                    with self._keys_lock:
                        keys_held = len(self._pressed_keys) > 0

                self.ctrl.set_brightness(base)
                self._keypress_event.clear()
                self._keyrelease_event.clear()
                self._wait(0.04)
            else:
                # Constant Blinking
                dur = 0.12 / self.speed
                self._wait(dur)
                self.ctrl.set_brightness(base)
                self._keypress_event.clear()
                self._wait(0.04)

    def get_status(self):
        return {
            "running": self.running,
            "current_effect": self.current_effect,
            "speed": self.speed,
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

        if self.isChecked():
            background = QLinearGradient(rect.topLeft(), rect.bottomRight())
            background.setColorAt(0.0, QColor("#123a51"))
            background.setColorAt(1.0, QColor("#0b2638"))
            border = QColor("#55c9ff")
            name_color = QColor("#f5fbff")
            desc_color = QColor("#a9daf2")
            icon_color = QColor("#67d3ff")
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
        self._build_ui()
        self._effect_changed()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(500)
        self._refresh_status()

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
        startup_note = QLabel("Launches elevated through Windows Task Scheduler")
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
        footer = QLabel("THRASH  •  VERSION 2.1  •  PRIVATE, LOCAL HARDWARE CONTROL")
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
        self.status_timer.stop()
        self.engine.stop()
        self.ctrl.shutdown()
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

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Lenovo LOQ Backlit Effects - Thrash")
    qt_app.setApplicationDisplayName("Lenovo LOQ Backlit Effects - Thrash")
    qt_app.setOrganizationName("Thrash")
    qt_app.setWindowIcon(QIcon(resource_path(os.path.join("assets", "app-icon.png"))))
    qt_app.setFont(QFont("Segoe UI Variable Text", 10))

    splash = BootSplash()
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
        window.show()
        splash.close()

    boot_timer.timeout.connect(finish_boot)
    boot_timer.start(45)
    sys.exit(qt_app.exec())
