# -*- mode: python ; coding: utf-8 -*-
"""
Receita do PyInstaller para gerar o RecorteManual.exe (arquivo unico, sem
console). A logomarca do GAAA e o icone viajam dentro do executavel e sao
localizados em tempo de execucao por `recorte_manual.caminho_recurso`.

Para gerar:
    .venv\\Scripts\\pyinstaller.exe RecorteManual.spec --noconfirm
"""

a = Analysis(
    ['recorte_manual.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/gaaa_logo.jpg', 'assets'),
        ('assets/gaaa.ico', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # o programa so precisa de Tkinter + Pillow; cortar o resto reduz o .exe
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
    name='RecorteManual',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # aplicativo de janela: nao abre o prompt preto
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/gaaa.ico',
    version='versao_exe.txt',
)
