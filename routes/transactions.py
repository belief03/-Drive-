# -*- coding: utf-8 -*-
"""取引登録・一覧。"""
import csv
import os
from io import BytesIO, StringIO
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, send_from_directory, send_file, abort, session
from models import db, Account, Transaction, Setting
from services import get_expense_account_suggestion, check_expense_account_consistency

bp = Blueprint("transactions", __name__)

RECEIPT_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
RECEIPT_MAX_SIZE = 10 * 1024 * 1024  # 10MB


def _receipt_allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in RECEIPT_ALLOWED_EXTENSIONS


def _save_receipt_file(file, transaction_id):
    """アップロードされた領収書画像を instance/receipts に保存し、相対パスを返す。"""
    if not file or not file.filename or not _receipt_allowed(file.filename):
        return None
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > RECEIPT_MAX_SIZE:
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext == "jpeg":
        ext = "jpg"
    safe = f"{transaction_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    receipts_dir = os.path.join(current_app.instance_path, "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    path = os.path.join(receipts_dir, safe)
    file.save(path)
    return os.path.join("receipts", safe).replace("\\", "/")


def _save_receipt_bytes(content, filename, transaction_id):
    """バイト列の領収書画像を instance/receipts に保存し、相対パスを返す。ドライブ取込用。"""
    if not content or not filename or not _receipt_allowed(filename):
        return None
    if len(content) > RECEIPT_MAX_SIZE:
        return None
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else "jpg"
    if ext == "jpeg":
        ext = "jpg"
    safe = f"{transaction_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    receipts_dir = os.path.join(current_app.instance_path, "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    path = os.path.join(receipts_dir, safe)
    with open(path, "wb") as f:
        f.write(content)
    return os.path.join("receipts", safe).replace("\\", "/")


def _delete_receipt_file(relative_path):
    """領収書画像ファイルを削除する。"""
    if not relative_path or ".." in relative_path or relative_path.startswith("/"):
        return
    path = os.path.join(current_app.instance_path, relative_path)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass

TRANSACTION_TYPES = [
    ("sales", "売上"),
    ("misc_income", "雑収入"),
    ("expense", "経費"),
    ("transfer", "振替"),
    ("loan", "借入・返済"),
    ("owner", "事業主貸・事業主借"),
    ("other", "その他"),
]


def get_asset_accounts():
    return Account.query.filter_by(category="asset", is_active=True).order_by(Account.code).all()


def get_expense_accounts():
    return Account.query.filter_by(category="expense", is_active=True).order_by(
        Account.common_expense_order, Account.code
    ).all()


def get_common_expense_accounts():
    return Account.query.filter_by(
        category="expense", is_common_expense=True, is_active=True
    ).order_by(Account.common_expense_order).all()


def get_all_accounts_for_transfer():
    return Account.query.filter(Account.category.in_(["asset", "liability", "expense"]), Account.is_active).order_by(Account.code).all()


@bp.route("/")
def list_transactions():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    filter_from = request.args.get("from", "").strip()
    filter_to = request.args.get("to", "").strip()
    q = Transaction.query.order_by(Transaction.date.asc(), Transaction.id.asc())
    if filter_from:
        try:
            from_date = datetime.strptime(filter_from, "%Y-%m-%d").date()
            q = q.filter(Transaction.date >= from_date)
        except ValueError:
            filter_from = ""
    if filter_to:
        try:
            to_date = datetime.strptime(filter_to, "%Y-%m-%d").date()
            q = q.filter(Transaction.date <= to_date)
        except ValueError:
            filter_to = ""
    pagination = q.paginate(page=page, per_page=per_page)
    asset_accounts = get_asset_accounts()
    sheets_created_url = session.pop("sheets_created_url", None)
    show_sheets_created = request.args.get("sheets_created") == "1" or sheets_created_url
    return render_template(
        "transactions/list.html",
        pagination=pagination,
        transaction_types=dict(TRANSACTION_TYPES),
        asset_accounts=asset_accounts,
        filter_from=filter_from,
        filter_to=filter_to,
        sheets_created_url=sheets_created_url,
        show_sheets_created=show_sheets_created,
    )


@bp.route("/export/csv")
def export_csv():
    """取引一覧をCSVでダウンロード。期間絞り込み（from/to）があれば同じ範囲をエクスポート。"""
    filter_from = request.args.get("from", "").strip()
    filter_to = request.args.get("to", "").strip()
    q = Transaction.query
    if filter_from:
        try:
            from_date = datetime.strptime(filter_from, "%Y-%m-%d").date()
            q = q.filter(Transaction.date >= from_date)
        except ValueError:
            pass
    if filter_to:
        try:
            to_date = datetime.strptime(filter_to, "%Y-%m-%d").date()
            q = q.filter(Transaction.date <= to_date)
        except ValueError:
            pass
    rows = _transaction_rows_for_export(q)
    buf = StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    buf.seek(0)
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM付きUTF-8（Excelで文字化けしにくい）
    name = "transactions"
    if filter_from and filter_to:
        name = f"transactions_{filter_from}_{filter_to}"
    elif filter_from:
        name = f"transactions_{filter_from}_"
    elif filter_to:
        name = f"transactions_{filter_to}"
    resp = send_file(
        BytesIO(csv_bytes),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{name}.csv",
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _transaction_rows_for_export(q):
    """CSV/スプレッドシート用の見出し行＋データ行のリストを返す。取引タイプは日本語ラベルで出力。"""
    type_labels = dict(TRANSACTION_TYPES)
    rows = q.order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    header = ["日付", "取引タイプ", "借方科目", "貸方科目", "金額", "取引先", "摘要", "領収書保管済"]
    data = [
        [
            r.date.isoformat() if r.date else "",
            type_labels.get(r.transaction_type, r.transaction_type),
            r.debit_account.name if r.debit_account else "",
            r.credit_account.name if r.credit_account else "",
            r.amount,
            r.payee or "",
            r.description or "",
            "○" if r.receipt_kept else "",
        ]
        for r in rows
    ]
    return [header] + data


@bp.route("/export/sheets")
def export_to_sheets():
    """取引一覧をGoogleスプレッドシートに新規作成して共有。期間絞り込み（from/to）に対応。"""
    try:
        from drive_service import get_sheets_service, create_spreadsheet_with_values, is_connected
    except ImportError:
        return redirect(url_for("transactions.list_transactions", sheets_error="no_module"))
    if not is_connected(_get_setting):
        return redirect(url_for("transactions.list_transactions", sheets_error="not_connected"))

    filter_from = request.args.get("from", "").strip()
    filter_to = request.args.get("to", "").strip()
    q = Transaction.query
    if filter_from:
        try:
            from_date = datetime.strptime(filter_from, "%Y-%m-%d").date()
            q = q.filter(Transaction.date >= from_date)
        except ValueError:
            pass
    if filter_to:
        try:
            to_date = datetime.strptime(filter_to, "%Y-%m-%d").date()
            q = q.filter(Transaction.date <= to_date)
        except ValueError:
            pass

    rows = _transaction_rows_for_export(q)
    if not rows or len(rows) <= 1:
        params = {"sheets_error": "no_data"}
        if filter_from:
            params["from"] = filter_from
        if filter_to:
            params["to"] = filter_to
        return redirect(url_for("transactions.list_transactions", **params))

    service = get_sheets_service(_get_setting, _set_setting)
    if not service:
        return redirect(url_for("transactions.list_transactions", sheets_error="service"))

    title = "取引一覧"
    if filter_from and filter_to:
        title = f"取引一覧 {filter_from}～{filter_to}"
    elif filter_from:
        title = f"取引一覧 {filter_from}～"
    elif filter_to:
        title = f"取引一覧 ～{filter_to}"

    sid, url, sheets_hint = create_spreadsheet_with_values(service, title, rows)
    if not url:
        params = {"sheets_error": "create_failed"}
        if sheets_hint:
            params["sheets_hint"] = sheets_hint
        if filter_from:
            params["from"] = filter_from
        if filter_to:
            params["to"] = filter_to
        return redirect(url_for("transactions.list_transactions", **params))

    # URL をクエリに載せると長すぎて 404 や切り捨てになることがあるため、セッションに保存
    session["sheets_created_url"] = url
    params = {"sheets_created": "1"}
    if filter_from:
        params["from"] = filter_from
    if filter_to:
        params["to"] = filter_to
    return redirect(url_for("transactions.list_transactions", **params))


@bp.route("/new", methods=["GET"])
def new_transaction():
    ttype = request.args.get("type", "expense")
    if ttype not in [t[0] for t in TRANSACTION_TYPES]:
        ttype = "expense"
    asset_accounts = get_asset_accounts()
    expense_accounts = get_expense_accounts()
    common_expense = get_common_expense_accounts()
    all_for_transfer = get_all_accounts_for_transfer()
    drive_receipt_available = bool(current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"))
    if drive_receipt_available:
        try:
            from drive_service import is_connected
            drive_receipt_available = is_connected(_get_setting)
        except ImportError:
            drive_receipt_available = False
    saved_receipt_folder_id = _get_setting(RECEIPT_FOLDER_ID_KEY) if drive_receipt_available else ""
    pending_receipt_filename = session.get("pending_receipt_filename") or ""
    return render_template(
        "transactions/new.html",
        transaction_type=ttype,
        transaction_types=TRANSACTION_TYPES,
        asset_accounts=asset_accounts,
        expense_accounts=expense_accounts,
        common_expense_accounts=common_expense,
        all_accounts_transfer=all_for_transfer,
        drive_receipt_available=drive_receipt_available,
        saved_receipt_folder_id=saved_receipt_folder_id,
        pending_receipt_filename=pending_receipt_filename,
    )


@bp.route("/create", methods=["POST"])
def create_transaction():
    ttype = request.form.get("transaction_type", "expense")
    try:
        date_str = request.form.get("date")
        trans_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    except ValueError:
        trans_date = date.today()
    amount = request.form.get("amount", type=int) or 0
    payee = request.form.get("payee", "").strip() or None
    description = request.form.get("description", "").strip() or None
    payment_method = request.form.get("payment_method")
    qr_source = request.form.get("qr_source")
    receipt_kept = request.form.get("receipt_kept") == "1"
    receipt_memo = request.form.get("receipt_memo", "").strip() or None

    debit_id = request.form.get("debit_account_id", type=int)
    credit_id = request.form.get("credit_account_id", type=int)

    if ttype == "sales":
        credit_id = Account.query.filter_by(code="510").first().id  # 売上
        debit_id = request.form.get("debit_account_id", type=int)
    elif ttype == "misc_income":
        credit_id = Account.query.filter_by(code="520").first().id  # 雑収入
        debit_id = request.form.get("debit_account_id", type=int)
    elif ttype == "expense":
        debit_id = request.form.get("expense_account_id", type=int)  # 経費科目＝借方
        # 貸方：現金 / 普通預金 / 未払金
        if payment_method == "cash":
            credit_id = Account.query.filter_by(code="110").first().id
        elif payment_method == "transfer":
            credit_id = request.form.get("credit_account_id", type=int) or Account.query.filter_by(code="120").first().id
        elif payment_method == "credit":
            credit_id = Account.query.filter_by(code="330").first().id  # 未払金
        elif payment_method == "qr":
            if qr_source == "credit":
                credit_id = Account.query.filter_by(code="330").first().id
            else:
                credit_id = request.form.get("credit_account_id", type=int) or Account.query.filter_by(code="120").first().id
        else:
            credit_id = Account.query.filter_by(code="120").first().id
    elif ttype == "transfer":
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)
    elif ttype == "loan":
        is_borrow = request.form.get("loan_type") == "borrow"
        if is_borrow:
            debit_id = request.form.get("debit_account_id", type=int)
            credit_id = Account.query.filter_by(code="320").first().id  # 借入金
        else:
            debit_id = Account.query.filter_by(code="320").first().id
            credit_id = request.form.get("credit_account_id", type=int)
    elif ttype == "owner":
        is_owner_lend = request.form.get("owner_type") == "owner_lend"  # 事業主貸＝事業→私用
        if is_owner_lend:
            debit_id = Account.query.filter_by(code="810").first().id  # 事業主貸
            credit_id = request.form.get("credit_account_id", type=int)
        else:
            debit_id = request.form.get("debit_account_id", type=int)
            credit_id = Account.query.filter_by(code="820").first().id  # 事業主借
    else:
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)

    if not debit_id or not credit_id or amount <= 0:
        return redirect(url_for("transactions.new_transaction", type=ttype))

    t = Transaction(
        transaction_type=ttype,
        date=trans_date,
        amount=amount,
        debit_account_id=debit_id,
        credit_account_id=credit_id,
        payee=payee,
        description=description,
        payment_method=payment_method if ttype == "expense" else None,
        qr_source=qr_source if ttype == "expense" and payment_method == "qr" else None,
        receipt_kept=receipt_kept if ttype == "expense" else False,
        receipt_memo=receipt_memo if ttype == "expense" else None,
    )
    db.session.add(t)
    db.session.commit()
    # 領収書画像: ファイルアップロード or ドライブから選択済み（セッションの一時ファイル）
    receipt_file = request.files.get("receipt_file")
    if receipt_file and receipt_file.filename:
        path = _save_receipt_file(receipt_file, t.id)
        if path:
            t.receipt_path = path
            db.session.commit()
    elif ttype == "expense" and session.get("pending_receipt_path"):
        pending_path = session.pop("pending_receipt_path", None)
        session.pop("pending_receipt_filename", None)
        if pending_path and not pending_path.startswith("/") and ".." not in pending_path:
            full_pending = os.path.join(current_app.instance_path, pending_path)
            if os.path.isfile(full_pending):
                ext = (pending_path.rsplit(".", 1)[-1] if "." in pending_path else "jpg").lower()
                if ext == "jpeg":
                    ext = "jpg"
                final_name = f"{t.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
                receipts_dir = os.path.join(current_app.instance_path, "receipts")
                final_path = os.path.join(receipts_dir, final_name)
                try:
                    import shutil
                    shutil.move(full_pending, final_path)
                    t.receipt_path = os.path.join("receipts", final_name).replace("\\", "/")
                    db.session.commit()
                except OSError:
                    try:
                        os.remove(full_pending)
                    except OSError:
                        pass
    return redirect(url_for("transactions.list_transactions"))


@bp.route("/<int:id>/edit", methods=["GET"])
def edit_transaction(id):
    t = Transaction.query.get_or_404(id)
    asset_accounts = get_asset_accounts()
    expense_accounts = get_expense_accounts()
    common_expense = get_common_expense_accounts()
    all_for_transfer = get_all_accounts_for_transfer()
    # 経費の支払方法をDBまたは貸方科目から復元
    payment_method = t.payment_method if t.transaction_type == "expense" else ""
    if t.transaction_type == "expense" and not payment_method and t.credit_account:
        if t.credit_account.code == "110":
            payment_method = "cash"
        elif t.credit_account.code == "330":
            payment_method = "qr" if t.qr_source else "credit"
        else:
            payment_method = "transfer"
    return render_template(
        "transactions/edit.html",
        transaction=t,
        transaction_types=dict(TRANSACTION_TYPES),
        asset_accounts=asset_accounts,
        expense_accounts=expense_accounts,
        common_expense_accounts=common_expense,
        all_accounts_transfer=all_for_transfer,
        payment_method_override=payment_method,
    )


@bp.route("/<int:id>/update", methods=["POST"])
def update_transaction(id):
    t = Transaction.query.get_or_404(id)
    ttype = t.transaction_type  # 編集では取引タイプは変更しない
    try:
        date_str = request.form.get("date")
        trans_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else t.date
    except ValueError:
        trans_date = t.date
    amount = request.form.get("amount", type=int) or t.amount
    payee = request.form.get("payee", "").strip() or None
    description = request.form.get("description", "").strip() or None
    payment_method = request.form.get("payment_method")
    qr_source = request.form.get("qr_source")
    receipt_kept = request.form.get("receipt_kept") == "1"
    receipt_memo = request.form.get("receipt_memo", "").strip() or None

    debit_id = request.form.get("debit_account_id", type=int)
    credit_id = request.form.get("credit_account_id", type=int)

    if ttype == "sales":
        credit_id = Account.query.filter_by(code="510").first().id
        debit_id = request.form.get("debit_account_id", type=int)
    elif ttype == "misc_income":
        credit_id = Account.query.filter_by(code="520").first().id
        debit_id = request.form.get("debit_account_id", type=int)
    elif ttype == "expense":
        debit_id = request.form.get("expense_account_id", type=int)
        if payment_method == "cash":
            credit_id = Account.query.filter_by(code="110").first().id
        elif payment_method == "transfer":
            credit_id = request.form.get("credit_account_id", type=int) or Account.query.filter_by(code="120").first().id
        elif payment_method == "credit":
            credit_id = Account.query.filter_by(code="330").first().id
        elif payment_method == "qr":
            if qr_source == "credit":
                credit_id = Account.query.filter_by(code="330").first().id
            else:
                credit_id = request.form.get("credit_account_id", type=int) or Account.query.filter_by(code="120").first().id
        else:
            credit_id = request.form.get("credit_account_id", type=int) or Account.query.filter_by(code="120").first().id
    elif ttype == "transfer":
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)
    elif ttype == "loan":
        is_borrow = request.form.get("loan_type") == "borrow"
        if is_borrow:
            debit_id = request.form.get("debit_account_id", type=int)
            credit_id = Account.query.filter_by(code="320").first().id
        else:
            debit_id = Account.query.filter_by(code="320").first().id
            credit_id = request.form.get("credit_account_id", type=int)
    elif ttype == "owner":
        is_owner_lend = request.form.get("owner_type") == "owner_lend"
        if is_owner_lend:
            debit_id = Account.query.filter_by(code="810").first().id
            credit_id = request.form.get("credit_account_id", type=int)
        else:
            debit_id = request.form.get("debit_account_id", type=int)
            credit_id = Account.query.filter_by(code="820").first().id
    else:
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)

    if not debit_id or not credit_id or amount <= 0:
        return redirect(url_for("transactions.edit_transaction", id=t.id))

    t.date = trans_date
    t.amount = amount
    t.debit_account_id = debit_id
    t.credit_account_id = credit_id
    t.payee = payee
    t.description = description
    if ttype == "expense":
        t.payment_method = payment_method
        t.qr_source = qr_source if payment_method == "qr" else None
        t.receipt_kept = receipt_kept
        t.receipt_memo = receipt_memo
    # 領収書画像：削除指定または新規アップロード
    if request.form.get("delete_receipt") == "1" and t.receipt_path:
        _delete_receipt_file(t.receipt_path)
        t.receipt_path = None
    receipt_file = request.files.get("receipt_file")
    if receipt_file and receipt_file.filename:
        if t.receipt_path:
            _delete_receipt_file(t.receipt_path)
        path = _save_receipt_file(receipt_file, t.id)
        if path:
            t.receipt_path = path
    db.session.commit()
    return redirect(url_for("transactions.list_transactions"))


@bp.route("/<int:id>/delete", methods=["POST"])
def delete_transaction(id):
    """取引を削除する。紐づく領収書画像も削除する。"""
    t = Transaction.query.get_or_404(id)
    if t.receipt_path:
        _delete_receipt_file(t.receipt_path)
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for("transactions.list_transactions", deleted=1))


@bp.route("/<int:id>/receipt")
def serve_receipt(id):
    """取引に紐づく領収書画像を返す。"""
    t = Transaction.query.get_or_404(id)
    if not t.receipt_path or ".." in t.receipt_path or t.receipt_path.startswith("/"):
        abort(404)
    full = os.path.join(current_app.instance_path, t.receipt_path)
    if not os.path.isfile(full):
        abort(404)
    return send_from_directory(
        current_app.instance_path,
        t.receipt_path,
        as_attachment=False,
        download_name=None,
    )


@bp.route("/<int:id>/mark_paid", methods=["POST"])
def mark_paid(id):
    """経費で貸方＝未払金の取引を「払い済み」にし、貸方を普通預金（または指定口座）に更新する。"""
    t = Transaction.query.get_or_404(id)
    if t.transaction_type != "expense" or not t.credit_account or t.credit_account.code != "330":
        return redirect(url_for("transactions.list_transactions"))
    # 指定があればその口座、なければ普通預金（code 120）
    account_id = request.form.get("credit_account_id", type=int)
    if account_id:
        acc = Account.query.get(account_id)
        if acc and acc.category == "asset":
            t.credit_account_id = acc.id
            t.payment_method = "transfer" if acc.code != "110" else "cash"
    else:
        default = Account.query.filter_by(code="120", is_active=True).first()
        if not default:
            default = Account.query.filter_by(category="asset", is_active=True).order_by(Account.code).first()
        if default:
            t.credit_account_id = default.id
            t.payment_method = "transfer"
    t.qr_source = None
    db.session.commit()
    return redirect(url_for("transactions.list_transactions"))


@bp.route("/api/suggest-expense-account")
def api_suggest_expense_account():
    """取引先から経費勘定科目を提案（リード型）。"""
    payee = request.args.get("payee", "")
    result = get_expense_account_suggestion(payee)
    return jsonify(result)


@bp.route("/api/check-expense-consistency")
def api_check_expense_consistency():
    """選択した経費科目が同一取引先の過去と一致するかチェック。"""
    payee = request.args.get("payee", "")
    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return jsonify({"consistent": True, "alert": None})
    result = check_expense_account_consistency(payee, account_id)
    return jsonify(result)


def _get_setting(key, default=""):
    s = Setting.query.filter_by(key=key).first()
    return (s.value or default).strip() if s and s.value else (default.strip() if isinstance(default, str) else "")


def _set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s:
        s.value = value
    else:
        s = Setting(key=key, value=value)
        db.session.add(s)
    db.session.commit()


RECEIPT_FOLDER_ID_KEY = "google_drive_receipt_folder_id"


# ---------- 領収書をドライブから取込 ----------
def _normalize_folder_id(folder_id):
    if not folder_id or not isinstance(folder_id, str):
        return (folder_id or "").strip()
    folder_id = folder_id.strip()
    for sep in ("folders/", "/folders/"):
        if sep in folder_id:
            folder_id = folder_id.split(sep)[-1].split("/")[0].split("?")[0]
            break
    return folder_id


@bp.route("/receipts/from-drive", methods=["GET"])
def receipts_from_drive():
    """ドライブのフォルダ内の画像を領収書として取込。フォルダIDで一覧表示し、選択した画像で新規経費取引を作成。"""
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return render_template("transactions/receipts_from_drive.html", drive_available=False)
    try:
        from drive_service import get_drive_service, is_connected, list_files_in_folder
    except ImportError:
        return render_template("transactions/receipts_from_drive.html", drive_available=False)
    if not is_connected(_get_setting):
        return render_template("transactions/receipts_from_drive.html", drive_available=True, drive_connected=False)

    folder_id = request.args.get("folder_id", "").strip()
    folder_id = _normalize_folder_id(folder_id) if folder_id else ""
    if not folder_id:
        saved = _get_setting(RECEIPT_FOLDER_ID_KEY)
        return render_template(
            "transactions/receipts_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=saved,
        )

    service = get_drive_service(_get_setting)
    if not service:
        return render_template(
            "transactions/receipts_from_drive.html",
            drive_available=True, drive_connected=True, folder_id=folder_id,
            error="Drive に接続できません",
        )
    try:
        files = list_files_in_folder(service, folder_id)
        _set_setting(RECEIPT_FOLDER_ID_KEY, folder_id)
        image_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        image_files = [f for f in files if (f.get("name") or "").lower().endswith(image_ext)]
        other_files = [f for f in files if f not in image_files]
        return render_template(
            "transactions/receipts_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=folder_id,
            image_files=image_files,
            other_files=other_files,
        )
    except Exception as e:
        return render_template(
            "transactions/receipts_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=folder_id,
            image_files=[],
            other_files=[],
            error=f"フォルダの取得に失敗しました: {e}",
        )


@bp.route("/receipts/from-drive/pick")
def receipts_from_drive_pick():
    """指定したドライブの画像をダウンロードし、領収書付きの新規経費取引を作成して編集画面へ。"""
    file_id = request.args.get("file_id")
    filename = request.args.get("filename", "receipt.jpg")
    if not file_id:
        return redirect(url_for("transactions.receipts_from_drive"))
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return redirect(url_for("transactions.list_transactions"))
    try:
        from drive_service import get_drive_service, is_connected, get_file_content
    except ImportError:
        return redirect(url_for("transactions.list_transactions"))
    if not is_connected(_get_setting):
        return redirect(url_for("transactions.receipts_from_drive"))
    service = get_drive_service(_get_setting)
    if not service:
        return redirect(url_for("transactions.receipts_from_drive"))
    if not _receipt_allowed(filename):
        return redirect(url_for("transactions.receipts_from_drive"))
    try:
        content = get_file_content(service, file_id)
    except Exception:
        return redirect(url_for("transactions.receipts_from_drive") + "?error=download")

    default_expense = Account.query.filter_by(category="expense", is_active=True).order_by(Account.code).first()
    default_credit = Account.query.filter_by(code="120", is_active=True).first()
    if not default_credit:
        default_credit = Account.query.filter_by(category="asset", is_active=True).order_by(Account.code).first()
    if not default_expense or not default_credit:
        return redirect(url_for("transactions.list_transactions"))

    t = Transaction(
        transaction_type="expense",
        date=date.today(),
        amount=0,
        debit_account_id=default_expense.id,
        credit_account_id=default_credit.id,
        payee=None,
        description="ドライブから取込",
        payment_method="transfer",
        receipt_kept=False,
        receipt_memo=None,
    )
    db.session.add(t)
    db.session.commit()
    path = _save_receipt_bytes(content, filename, t.id)
    if path:
        t.receipt_path = path
        db.session.commit()
    return redirect(url_for("transactions.edit_transaction", id=t.id))


# ---------- 取引登録画面からドライブの領収書を選択 ----------
@bp.route("/new/pick-receipt-from-drive", methods=["GET"])
def new_pick_receipt_from_drive():
    """取引登録用。ドライブのフォルダから領収書画像を1枚選び、セッションに保持して取引登録に戻る。フォルダIDは記憶する。"""
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return redirect(url_for("transactions.new_transaction", type="expense"))
    try:
        from drive_service import get_drive_service, is_connected, list_files_in_folder
    except ImportError:
        return redirect(url_for("transactions.new_transaction", type="expense"))
    if not is_connected(_get_setting):
        return redirect(url_for("transactions.new_transaction", type="expense"))

    folder_id = request.args.get("folder_id", "").strip()
    folder_id = _normalize_folder_id(folder_id) if folder_id else _get_setting(RECEIPT_FOLDER_ID_KEY)
    if not folder_id:
        return render_template(
            "transactions/new_pick_receipt_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id="",
            image_files=[],
            other_files=[],
        )
    service = get_drive_service(_get_setting)
    if not service:
        return render_template(
            "transactions/new_pick_receipt_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=folder_id,
            image_files=[],
            other_files=[],
            error="Drive に接続できません",
        )
    try:
        files = list_files_in_folder(service, folder_id)
        _set_setting(RECEIPT_FOLDER_ID_KEY, folder_id)
        image_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        image_files = [f for f in files if (f.get("name") or "").lower().endswith(image_ext)]
        other_files = [f for f in files if f not in image_files]
        return render_template(
            "transactions/new_pick_receipt_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=folder_id,
            image_files=image_files,
            other_files=other_files,
        )
    except Exception as e:
        return render_template(
            "transactions/new_pick_receipt_from_drive.html",
            drive_available=True,
            drive_connected=True,
            folder_id=folder_id,
            image_files=[],
            other_files=[],
            error=f"フォルダの取得に失敗しました: {e}",
        )


@bp.route("/new/pick-receipt-from-drive/pick")
def new_pick_receipt_from_drive_pick():
    """ドライブの画像を1枚ダウンロードし、一時保存してセッションに記録。取引登録画面に戻る。"""
    file_id = request.args.get("file_id")
    filename = request.args.get("filename", "receipt.jpg")
    if not file_id or not _receipt_allowed(filename):
        return redirect(url_for("transactions.new_transaction", type="expense"))
    try:
        from drive_service import get_drive_service, is_connected, get_file_content
    except ImportError:
        return redirect(url_for("transactions.new_transaction", type="expense"))
    if not is_connected(_get_setting):
        return redirect(url_for("transactions.new_transaction", type="expense"))
    service = get_drive_service(_get_setting)
    if not service:
        return redirect(url_for("transactions.new_transaction", type="expense"))
    try:
        content = get_file_content(service, file_id)
    except Exception:
        return redirect(url_for("transactions.new_pick_receipt_from_drive") + "?error=download")
    if len(content) > RECEIPT_MAX_SIZE:
        return redirect(url_for("transactions.new_pick_receipt_from_drive"))
    import uuid
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "jpg").lower()
    if ext == "jpeg":
        ext = "jpg"
    safe_name = f"pending_{uuid.uuid4().hex}.{ext}"
    receipts_dir = os.path.join(current_app.instance_path, "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    pending_path = os.path.join(receipts_dir, safe_name)
    with open(pending_path, "wb") as f:
        f.write(content)
    session["pending_receipt_path"] = os.path.join("receipts", safe_name).replace("\\", "/")
    session["pending_receipt_filename"] = filename
    return redirect(url_for("transactions.new_transaction", type="expense", receipt_picked=1))


@bp.route("/new/clear-pending-receipt")
def new_clear_pending_receipt():
    """取引登録で選択済みのドライブ領収書を解除する。"""
    pending_path = session.pop("pending_receipt_path", None)
    session.pop("pending_receipt_filename", None)
    if pending_path and ".." not in pending_path and not pending_path.startswith("/"):
        full = os.path.join(current_app.instance_path, pending_path)
        if os.path.isfile(full):
            try:
                os.remove(full)
            except OSError:
                pass
    return redirect(url_for("transactions.new_transaction", type="expense"))
