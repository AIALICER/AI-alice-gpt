# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\uchid\\AI-Alice\\tools\\bot_manager\\entry.py'],
    pathex=['C:\\Users\\uchid\\AI-Alice'],
    binaries=[],
    datas=[],
    hiddenimports=['tools.bot_manager.app', 'tools.bot_manager.scanner', 'tools.bot_manager.slash_catalog', 'tools.character_creator.messages_generator', 'tools.character_creator.messages_format', 'tools.character_creator.generator', 'tools.common.project_root', 'tools.common.gemini_keys', 'tools.common.gemini_messages_client', 'httpx', 'google.genai', 'dotenv'],
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
    name='AI-Alice-BotManager',
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
