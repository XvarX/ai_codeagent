# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['agentcore\\main.py'],
    pathex=[],
    binaries=[('agentcore/rg.exe', '.')],
    datas=[],
    hiddenimports=[
        'agentcore.ws_server', 'agentcore.flet_ui.app',
        'agentcore.providers.anthropic', 'agentcore.providers.openai_compat',
        'agentcore.tools.bash', 'agentcore.tools.file_read', 'agentcore.tools.file_edit',
        'agentcore.tools.file_write', 'agentcore.tools.glob', 'agentcore.tools.grep',
        'agentcore.tools.agent_tool', 'agentcore.tools.send_message_tool',
        'agentcore.tools.tool_result_storage', 'agentcore.tools.registry',
        'agentcore.compact.compact', 'agentcore.compact.autoCompact',
        'agentcore.compact.prompt', 'agentcore.compact.grouping',
        'agentcore.compact.postCompactCleanup',
        'agentcore.skills.loader', 'agentcore.skills.skill_tool',
        'agentcore.mcp_integration.connection', 'agentcore.mcp_integration.config',
        'agentcore.agent_definitions', 'agentcore.subagent_manager',
        'agentcore.agent_message_queue', 'agentcore.controller',
        'mcp', 'mcp.client.stdio', 'websockets', 'yaml', 'flet',
    ],
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
    name='agentcore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='agentcore',
)
