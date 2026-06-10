# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['tools.character_creator.generator', 'tools.character_creator.app', 'tools.character_creator.project_patcher', 'tools.character_creator.messages_generator', 'tools.character_creator.messages_format', 'google.genai', 'dotenv', 'tools.common.project_root', 'tools.common.gemini_keys', 'tools.common.gemini_messages_client', 'httpx', 'requests', 'certifi']
hiddenimports += collect_submodules('certifi')


a = Analysis(
    ['C:\\Users\\uchid\\AI-Alice\\tools\\character_creator\\entry.py'],
    pathex=['C:\\Users\\uchid\\AI-Alice'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='AI-Alice-CharacterCreator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
