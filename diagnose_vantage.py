"""
Lenovo Vantage DLL Diagnostics & Compatibility Probe
================================================================================
Queries active Vantage modules, DLL contracts, registry settings, and system details
to debug keyboard backlight control mapping on unsupported Lenovo models.
"""

import os
import sys
import glob
import ctypes
import datetime
import subprocess

REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vantage_diagnose_report.txt")
lines = []

def log(msg=""):
    print(msg)
    lines.append(str(msg))

def save_report():
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def get_registry_value(path, name):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return str(val).strip()
    except Exception:
        return None

def main():
    log("=" * 70)
    log("  Lenovo Vantage Backlight Controller Diagnostic Report")
    log(f"  Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # 1. System Info
    log("\n[1] SYSTEM INFORMATION")
    log(f"  Admin Privileges : {'Yes (Elevated)' if is_admin() else 'No (Not Elevated)'}")
    log(f"  Python Version   : {sys.version}")
    log(f"  Windows Version  : {get_registry_value(r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'ProductName')} (Build {get_registry_value(r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuild')})")
    log(f"  Device Model     : {get_registry_value(r'HARDWARE\DESCRIPTION\System\BIOS', 'SystemProductName')}")
    log(f"  System Motherboard: {get_registry_value(r'HARDWARE\DESCRIPTION\System\BIOS', 'BaseBoardProduct')}")
    log(f"  BIOS Version     : {get_registry_value(r'HARDWARE\DESCRIPTION\System\BIOS', 'BIOSVersion')}")

    # 2. Vantage Addins Directory Scanner
    addins_root = r"C:\ProgramData\Lenovo\Vantage\Addins"
    log("\n[2] VANTAGE ADDINS FOLDER SCAN")
    if not os.path.exists(addins_root):
        log(f"  WARNING: Vantage Addins folder not found at path: {addins_root}")
        log("  Is Lenovo Vantage installed on this machine?")
        save_report()
        return

    log(f"  Root Addins Folder: {addins_root} (Found)")

    subdirs = [d for d in os.listdir(addins_root) if os.path.isdir(os.path.join(addins_root, d))]
    log(f"  Subdirectories found ({len(subdirs)}):")
    for d in subdirs:
        log(f"    - {d}")

    # 3. Locate Key Assemblies recursively
    log("\n[3] SEARCHING FOR LENOVO KEYBOARD/LIGHTING DLLs")
    search_patterns = [
        r"C:\ProgramData\Lenovo\Vantage\Addins\**\*Contract*.dll",
        r"C:\ProgramData\Lenovo\Vantage\Addins\**\*Addin*.dll",
        r"C:\ProgramData\Lenovo\Vantage\Addins\**\*Lighting*.dll"
    ]

    dll_paths = []
    for pattern in search_patterns:
        dll_paths.extend(glob.glob(pattern, recursive=True))

    dll_paths = sorted(list(set(dll_paths))) # Unique list
    if dll_paths:
        log(f"  Found {len(dll_paths)} lighting-related assemblies:")
        for p in dll_paths:
            size_kb = os.path.getsize(p) / 1024
            log(f"    - {p} ({size_kb:.1f} KB)")
    else:
        log("  No lighting or keyboard assemblies found! This model may use a different Vantage driver.")

    # 4. Check for active Vantage Services
    log("\n[4] LENOVO WINDOWS SERVICES STATUS")
    services = ["ImControllerService", "LenovoVantageService", "Lenovo.Modern.ImController"]
    for s in services:
        try:
            res = subprocess.check_output(f"powershell -NoProfile -Command \"Get-Service '{s}' -ErrorAction SilentlyContinue | Select-Object Status, DisplayName | Out-String\"", shell=True, text=True)
            status = res.strip()
            if status:
                log(f"  Service '{s}':\n    {status.replace('\n', '\n    ')}")
            else:
                log(f"  Service '{s}': Not Installed")
        except Exception:
            log(f"  Service '{s}': Error querying")

    log("\n" + "=" * 70)
    log("  DIAGNOSTICS COMPLETED")
    log(f"  Report saved to: {REPORT_FILE}")
    log("=" * 70)
    save_report()

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
