# -*- coding: utf-8 -*-
"""Render のデフォルト Start Command（gunicorn your_application.wsgi）用。
本番では Render の Start Command を 'gunicorn wsgi:application' に変更することを推奨。"""
from wsgi import application as wsgi
