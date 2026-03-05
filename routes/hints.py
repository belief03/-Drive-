# -*- coding: utf-8 -*-
"""科目のヒント一覧（こんな取引はどの科目？）。"""
import os
import json
from flask import Blueprint, render_template

bp = Blueprint("hints", __name__)

# ヒントデータのパス（プロジェクトルートの data/hints.json）
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HINTS_PATH = os.path.join(BASE_DIR, "data", "hints.json")

# フォールバック（ファイルがない場合）
DEFAULT_HINTS = [
    {"example": "印刷・コピー", "account": "消耗品費", "note": "オフィスでの印刷代"},
    {"example": "印刷（少額・雑多）", "account": "その他", "note": "領収書が「雑費」のときもその他で計上可"},
    {"example": "切手・はがき", "account": "通信費", "note": ""},
    {"example": "スマホ・携帯料金", "account": "通信費", "note": ""},
    {"example": "電車・バス・タクシー", "account": "旅費交通費", "note": ""},
    {"example": "文房具・用紙", "account": "消耗品費", "note": ""},
    {"example": "接待・飲食（取引先）", "account": "接待交際費", "note": ""},
    {"example": "振込手数料", "account": "支払手数料", "note": ""},
    {"example": "外注・発注先への支払", "account": "外注費", "note": ""},
    {"example": "少額の雑多な経費", "account": "その他", "note": "どの科目にも当てはまらないとき"},
]


def load_hints():
    if os.path.isfile(HINTS_PATH):
        try:
            with open(HINTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_HINTS


@bp.route("/")
def index():
    hints = load_hints()
    return render_template("hints/index.html", hints=hints)
