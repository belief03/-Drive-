# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, redirect, url_for, request
from models import db, Setting, Industry

bp = Blueprint("main", __name__)


def get_industry_setting():
    s = Setting.query.filter_by(key="industry").first()
    return s.value if s else None


@bp.route("/")
def index():
    industry = get_industry_setting()
    if industry is None:
        return redirect(url_for("main.setup"))
    return redirect(url_for("transactions.list_transactions"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """初期設定：業種選択（初回または設定から変更時）。"""
    if request.method == "POST":
        industry = request.form.get("industry", "").strip()
        if industry:
            s = Setting.query.filter_by(key="industry").first()
            if s:
                s.value = industry
            else:
                s = Setting(key="industry", value=industry)
                db.session.add(s)
            db.session.commit()
        return redirect(url_for("main.index"))
    industries = Industry.query.filter_by(is_active=True).order_by(Industry.display_order).all()
    current = get_industry_setting()
    return render_template("setup.html", industries=industries, current=current)
