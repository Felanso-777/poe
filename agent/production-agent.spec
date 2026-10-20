# PyInstaller spec for the consent-first Windows desktop agent.
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["windows_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("watchdog"),
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
    name="ProofOfEffortMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
