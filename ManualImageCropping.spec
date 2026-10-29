# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller recipe for ManualImageCropping.exe (single file, no console).
The GAAA logo and the icon travel inside the executable and are located at
runtime by `manual_cropping.resource_path`.

To build:
    .venv\Scripts\pyinstaller.exe ManualImageCropping.spec --noconfirm
"""

a = Analysis(
    ['manual_cropping.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/gaaa_logo.jpg', 'assets'),
        ('assets/app_icon.ico', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # the program only needs Tkinter + Pillow; dropping the rest shrinks the exe
    excludes=[
        'matplotlib', 'pandas', 'numpy', 'scipy', 'sklearn', 'seaborn',
        'IPython', 'jupyter', 'notebook', 'pytest', 'setuptools', 'pip',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ManualImageCropping',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed application: no black prompt
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
    version='exe_version.txt',
)
