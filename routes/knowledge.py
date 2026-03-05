# -*- coding: utf-8 -*-
"""税務・経理の知識・豆知識一覧。"""
import os
import json
from flask import Blueprint, render_template

bp = Blueprint("knowledge", __name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KNOWLEDGE_PATH = os.path.join(BASE_DIR, "data", "knowledge.json")

DEFAULT_KNOWLEDGE = [
    {
        "title": "30万円未満の備品は一括で経費にできる？",
        "summary": "少額減価償却資産の特例により、条件を満たせば30万円未満の資産をその年に一括で経費にできます。",
        "detail": "詳細は税理士または所轄税務署にご確認ください。",
    },
    {
        "title": "減価償却は何年で分ける？",
        "summary": "資産の種類ごとに法定耐用年数が決まっています。PCは5年、ソフトは3年など。",
        "detail": "国税庁の耐用年数表を参照し、毎年「減価償却費」として計上します。",
    },
]


def load_knowledge():
    if os.path.isfile(KNOWLEDGE_PATH):
        try:
            with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_KNOWLEDGE


@bp.route("/")
def index():
    items = load_knowledge()
    return render_template("knowledge/index.html", items=items)
