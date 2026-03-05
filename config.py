# -*- coding: utf-8 -*-
"""アプリ設定。法改正で変わりうる値はここで管理する。"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _read_drive_secret_file(filename):
    """instance 内のテキストファイルの1行目を返す（環境変数未設定時用）。"""
    path = os.path.join(BASE_DIR, "instance", filename)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.readline().strip()
        except Exception:
            pass
    return ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-change-in-production"
    # instance フォルダは Flask が app.instance_path で用意する。相対パスにするとカレントで解決される。
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "account_book.db").replace("\\", "/")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 保存期間（年）。帳簿・領収書の推奨保存期間。
    RECORD_RETENTION_YEARS = 7

    # Google Drive 連携（未設定なら連携機能は無効）
    # 環境変数が無い場合は instance フォルダのテキストファイルから読み込む（1行目が値）
    GOOGLE_DRIVE_CLIENT_ID = os.environ.get("GOOGLE_DRIVE_CLIENT_ID") or _read_drive_secret_file("google_drive_client_id.txt")
    GOOGLE_DRIVE_CLIENT_SECRET = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET") or _read_drive_secret_file("google_drive_client_secret.txt")
    GOOGLE_DRIVE_REDIRECT_URI = os.environ.get("GOOGLE_DRIVE_REDIRECT_URI") or "http://127.0.0.1:5000/settings/drive/callback"

    # 業種の選択肢（マスタで管理する場合はDBから読み込む。ここは初期値）
    INDUSTRY_CHOICES = [
        "IT・Web受託",
        "コンサル",
        "物販",
        "飲食",
        "士業",
        "その他",
    ]
