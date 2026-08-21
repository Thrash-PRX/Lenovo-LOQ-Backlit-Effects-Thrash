# PyInstaller build specification for Lenovo LOQ Keyboard Effects Lab.
# Build on Windows with: pyinstaller --clean --noconfirm keyboard-effects.spec

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets/app-icon.png", "assets"),
        ("assets/thrash-liquid-glass-v3.png", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LenovoLOQBacklitEffects-Thrash",
    version="version_info.txt",
    icon="assets/app.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
