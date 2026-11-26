# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/chouchamnan/samray_dubber_pro/main.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/chouchamnan/samray_dubber_pro/assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SamrayDubberPro',
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
    icon=['/Users/chouchamnan/samray_dubber_pro/samray.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SamrayDubberPro',
)
app = BUNDLE(
    coll,
    name='SamrayDubberPro.app',
    icon='/Users/chouchamnan/samray_dubber_pro/samray.icns',
    bundle_identifier='com.chamnan.samraydubberpro',
)
