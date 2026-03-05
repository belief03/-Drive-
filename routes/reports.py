# -*- coding: utf-8 -*-
"""レポート：P/L・B/S・エクスポート・領収書まとめ。"""
import os
from datetime import date, timedelta
from flask import Blueprint, render_template, request, send_file, current_app
from io import BytesIO
import csv
from models import db, Account, Transaction
from sqlalchemy import func

bp = Blueprint("reports", __name__)


def _receipts_query(start, end, account_id=None):
    """領収書画像がある取引を期間・科目で絞り込み。"""
    q = (
        Transaction.query.filter(
            Transaction.receipt_path.isnot(None),
            Transaction.receipt_path != "",
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
    )
    if account_id:
        q = q.filter(Transaction.debit_account_id == account_id)
    return q.all()


def get_pl_bs(year: int):
    """指定年の損益計算書・貸借対照表用の集計。"""
    start = date(year, 1, 1)
    end = date(year, 12, 31)

    # 収益・費用の合計（当年）
    revenue = (
        db.session.query(Account.id, Account.code, Account.name, func.coalesce(func.sum(Transaction.amount), 0).label("total"))
        .join(Transaction, Transaction.credit_account_id == Account.id)
        .filter(Account.category == "revenue", Transaction.date >= start, Transaction.date <= end)
        .group_by(Account.id, Account.code, Account.name)
        .all()
    )
    expense = (
        db.session.query(Account.id, Account.code, Account.name, func.coalesce(func.sum(Transaction.amount), 0).label("total"))
        .join(Transaction, Transaction.debit_account_id == Account.id)
        .filter(Account.category == "expense", Transaction.date >= start, Transaction.date <= end)
        .group_by(Account.id, Account.code, Account.name)
        .all()
    )
    total_revenue = sum(r.total for r in revenue)
    total_expense = sum(e.total for e in expense)
    profit = total_revenue - total_expense

    # 資産・負債・純資産の残高（年末時点＝当年までの累計）
    def balance_for_category(category):
        accounts = Account.query.filter_by(category=category, is_active=True).order_by(Account.code).all()
        rows = []
        for acc in accounts:
            debit_total = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
                Transaction.debit_account_id == acc.id, Transaction.date <= end
            ).scalar() or 0
            credit_total = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
                Transaction.credit_account_id == acc.id, Transaction.date <= end
            ).scalar() or 0
            if category in ("asset", "expense"):
                bal = debit_total - credit_total
            elif category == "owner":
                bal = debit_total - credit_total if acc.code == "810" else credit_total - debit_total
            else:
                bal = credit_total - debit_total
            if bal != 0:
                rows.append((acc.code, acc.name, int(bal)))
        return rows

    assets = balance_for_category("asset")
    liabilities = balance_for_category("liability")
    equity = balance_for_category("equity")
    owner_bal = balance_for_category("owner")

    return {
        "year": year,
        "revenue": revenue,
        "expense": expense,
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "profit": profit,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "owner_balance": owner_bal,
    }


@bp.route("/pl-bs")
def pl_bs():
    year = request.args.get("year", type=int) or date.today().year
    data = get_pl_bs(year)
    return render_template("reports/pl_bs.html", **data)


def export_csv_content(year: int):
    """指定年の取引CSVをバイト列で返す（ドライブバックアップ等で利用）。取引タイプは日本語ラベルで出力。"""
    from routes.transactions import TRANSACTION_TYPES
    type_labels = dict(TRANSACTION_TYPES)
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    rows = (
        Transaction.query.filter(Transaction.date >= start, Transaction.date <= end)
        .order_by(Transaction.date, Transaction.id)
        .all()
    )
    buf = BytesIO()
    w = csv.writer(buf)
    w.writerow(["日付", "取引タイプ", "借方科目", "貸方科目", "金額", "取引先", "摘要", "領収書保管済"])
    for r in rows:
        w.writerow([
            r.date.isoformat() if r.date else "",
            type_labels.get(r.transaction_type, r.transaction_type),
            r.debit_account.name if r.debit_account else "",
            r.credit_account.name if r.credit_account else "",
            r.amount,
            r.payee or "",
            r.description or "",
            "○" if r.receipt_kept else "",
        ])
    buf.seek(0)
    return buf.getvalue()


@bp.route("/export/csv")
def export_csv():
    """取引一覧をCSVエクスポート（確定申告用データの土台）。"""
    year = request.args.get("year", type=int) or date.today().year
    content = export_csv_content(year)
    resp = send_file(
        BytesIO(content),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"transactions_{year}.csv",
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@bp.route("/receipts")
def receipts():
    """領収書まとめページ。期間・科目で絞り込み、一覧表示とPDF出力。"""
    year = request.args.get("year", type=int) or date.today().year
    month = request.args.get("month", type=int)  # None = 通年
    account_id = request.args.get("account_id", type=int)

    if month:
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        period_label = f"{year}年{month}月"
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        period_label = f"{year}年"

    items = _receipts_query(start, end, account_id)
    expense_accounts = (
        Account.query.filter_by(category="expense", is_active=True)
        .order_by(Account.common_expense_order, Account.code)
        .all()
    )
    return render_template(
        "reports/receipts.html",
        year=year,
        month=month,
        period_label=period_label,
        items=items,
        expense_accounts=expense_accounts,
        account_id=account_id,
    )


def _build_receipts_pdf(instance_path, items, period_label):
    """領収書一覧を1つのPDFにまとめる。表紙＋各取引1ページ。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # 日本語表示用CIDフォントを登録（Helveticaは日本語非対応のため文字化けする）
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        font_name = "HeiseiMin-W3"
        font_bold = "HeiseiKakuGo-W5"
    except Exception:
        font_name = font_bold = "Helvetica"

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    margin = 20 * mm
    content_w = w - 2 * margin
    content_h = h - 2 * margin

    # 表紙
    c.setFont(font_bold, 18)
    c.drawCentredString(w / 2, h - 40 * mm, "領収書まとめ")
    c.setFont(font_name, 12)
    c.drawCentredString(w / 2, h - 55 * mm, f"対象期間: {period_label}")
    c.drawCentredString(w / 2, h - 70 * mm, f"件数: {len(items)} 件")
    c.showPage()

    for t in items:
        c.setFont(font_name, 10)
        y = h - margin
        c.drawString(margin, y, f"日付: {t.date.isoformat() if t.date else ''}")
        y -= 6 * mm
        c.drawString(margin, y, f"取引先: {t.payee or '—'}")
        y -= 6 * mm
        c.drawString(margin, y, f"金額: {t.amount:,} 円")
        y -= 6 * mm
        c.drawString(margin, y, f"勘定科目: {t.debit_account.name if t.debit_account else ''}")
        y -= 10 * mm

        if not t.receipt_path or ".." in t.receipt_path or t.receipt_path.startswith("/"):
            img_path = None
        else:
            img_path = os.path.join(instance_path, t.receipt_path)
        if img_path and os.path.isfile(img_path):
            try:
                img = ImageReader(img_path)
                iw, ih = img.getSize()
                max_w = content_w
                max_h = content_h - (h - margin - y)
                scale = min(max_w / iw, max_h / ih, 1.0)
                nw, nh = iw * scale, ih * scale
                c.drawImage(img_path, margin, y - nh, width=nw, height=nh)
            except Exception:
                c.drawString(margin, y - 5 * mm, "(画像の読み込みに失敗しました)")
        else:
            c.drawString(margin, y - 5 * mm, "(画像なし)")
        c.showPage()

    c.save()
    buf.seek(0)
    return buf


@bp.route("/receipts/pdf")
def receipts_pdf():
    """領収書まとめをPDFでダウンロード。"""
    year = request.args.get("year", type=int) or date.today().year
    month = request.args.get("month", type=int)
    account_id = request.args.get("account_id", type=int)

    if month:
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        period_label = f"{year}年{month}月"
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        period_label = f"{year}年"

    items = _receipts_query(start, end, account_id)
    if not items:
        from flask import redirect, url_for
        params = {"year": year}
        if month:
            params["month"] = month
        if account_id:
            params["account_id"] = account_id
        return redirect(url_for("reports.receipts", **params))

    instance_path = current_app.instance_path
    buf = _build_receipts_pdf(instance_path, items, period_label)
    filename = f"receipts_{year}" + (f"_{month:02d}" if month else "") + ".pdf"
    resp = send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def build_receipts_pdf_bytes(year: int, month=None, account_id=None):
    """指定期間の領収書まとめPDFをバイト列で返す。対象が0件なら None。"""
    from calendar import monthrange
    if month:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        period_label = f"{year}年{month}月"
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        period_label = f"{year}年"
    items = _receipts_query(start, end, account_id)
    if not items:
        return None
    instance_path = current_app.instance_path
    buf = _build_receipts_pdf(instance_path, items, period_label)
    return buf.getvalue()
