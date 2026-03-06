# -*- coding: utf-8 -*-
"""WSGI エントリポイント（PythonAnywhere や Gunicorn 用）。"""
import sys
import os

# プロジェクトルートをパスに追加（PythonAnywhere で clone したディレクトリ）
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

from app import app as application
