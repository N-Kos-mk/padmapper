"""ダブルクリックでタスクトレイに常駐させる (コンソールウィンドウは出ない)。

既に起動している場合は、起動中の padmapper の設定画面を開く。
"""

import sys

from padmapper.__main__ import main

sys.exit(main(["--tray"]))
