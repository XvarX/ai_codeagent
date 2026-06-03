"""Entry point — delegates to agentcore.main.

python main.py                  Flet 桌面界面 (默认)
python main.py -s               终端交互模式
python main.py -c "message"     单次命令行模式
python main.py --ws --port 18765  WebSocket server 模式
"""

import asyncio
import sys

if __name__ == "__main__":
    if len(sys.argv) == 1:
        from agentcore.config import AgentConfig
        from agentcore.flet_ui.app import launch_flet
        launch_flet(AgentConfig.from_yaml())
    else:
        from agentcore.main import main
        asyncio.run(main())
