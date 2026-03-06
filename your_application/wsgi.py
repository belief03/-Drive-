# -*- coding: utf-8 -*-
"""gunicorn your_application.wsgi で参照される WSGI アプリ。ルートの wsgi をそのまま使う。"""
import sys
import os

# プロジェクトルートをパスに追加（Render の作業ディレクトリが src 等の場合に備える）
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(_root)

from wsgi import application
