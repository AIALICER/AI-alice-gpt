#!/usr/bin/env python3
"""Bot 設定マネージャ起動スクリプト。"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.bot_manager.entry import main

if __name__ == "__main__":
    main()
