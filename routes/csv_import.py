# -*- coding: utf-8 -*-
"""CSV取込：銀行・クレジット明細の一括取込、マッピング、重複防止。"""
import csv
import io
import re
from calendar import monthrange
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app
from models import db, Account, Transaction, Setting

bp = Blueprint("csv_import", __name__, url_prefix="/transactions/import")


def _get_setting(key: str, default: str = "") -> str:
    s = Setting.query.filter_by(key=key).first()
    if s is None or s.value is None:
        return default.strip() if isinstance(default, str) else ""
    return (s.value or default).strip()


def get_asset_accounts():
    return Account.query.filter_by(category="asset", is_active=True).order_by(Account.code).all()


def get_expense_accounts():
    return Account.query.filter_by(category="expense", is_active=True).order_by(
        Account.common_expense_order, Account.code
    ).all()


def parse_date(s):
    if not s or not str(s).strip():
        return None
    s = str(s).strip().replace(" ", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%y-%m-%d", "%y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def parse_amount(s):
    if s is None or s == "":
        return None
    s = str(s).strip().replace(",", "").replace("円", "")
    try:
        return int(s)
    except ValueError:
        return None


def is_duplicate(d: date, amount: int, payee: str) -> bool:
    if not d or amount is None:
        return False
    start = date(d.year, d.month, 1)
    end = date(d.year, d.month, monthrange(d.year, d.month)[1])
    q = Transaction.query.filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.amount == amount,
    )
    if payee:
        q = q.filter(Transaction.payee.ilike(f"%{(payee or '')[:50]}%"))
    return q.first() is not None


def _parse_csv_to_candidates(text, has_header, col_date, col_amount, col_payee):
    """CSV テキストをパースして candidates リストを返す。"""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if has_header and rows:
        rows = rows[1:]
    candidates = []
    for row in rows:
        if max(col_date, col_amount, col_payee) >= len(row):
            continue
        d = parse_date(row[col_date])
        amount = parse_amount(row[col_amount])
        payee = (row[col_payee] or "").strip() or None
        if d and amount is not None and amount != 0:
            candidates.append({
                "date": d,
                "amount": amount,
                "payee": payee,
                "duplicate": is_duplicate(d, amount, payee or ""),
            })
    return candidates


@bp.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        from_drive = session.get("csv_import_drive_filename")
        return render_template(
            "csv_import/upload.html",
            from_drive_filename=from_drive,
        )

    # Drive から取得した CSV をセッションに持っている場合
    text = session.pop("csv_import_drive_content", None)
    filename = session.pop("csv_import_drive_filename", None)
    if text is not None:
        pass  # 下の has_header/col_* でパースする
    else:
        file = request.files.get("csv_file")
        if not file or not file.filename:
            return render_template("csv_import/upload.html", error="ファイルを選択してください")
        try:
            raw = file.read()
            if raw.startswith(b"\xef\xbb\xbf"):
                text = raw.decode("utf-8-sig")
            else:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("cp932")
        except Exception as e:
            return render_template("csv_import/upload.html", error=f"ファイルの読み込みに失敗しました: {e}")

    has_header = request.form.get("has_header") == "1"
    col_date = int(request.form.get("col_date", 0))
    col_amount = int(request.form.get("col_amount", 1))
    col_payee = int(request.form.get("col_payee", 2))

    candidates = _parse_csv_to_candidates(text, has_header, col_date, col_amount, col_payee)
    session["csv_import_candidates"] = [
        {"date": c["date"].isoformat(), "amount": c["amount"], "payee": c["payee"], "duplicate": c["duplicate"]}
        for c in candidates
    ]
    return redirect(url_for("csv_import.preview"))


@bp.route("/preview", methods=["GET", "POST"])
def preview():
    candidates = session.get("csv_import_candidates")
    if not candidates:
        return redirect(url_for("csv_import.upload"))

    if request.method == "POST":
        default_credit_id = request.form.get("default_credit_account_id", type=int)
        if not default_credit_id:
            default_acc = Account.query.filter_by(code="120").first()
            default_credit_id = default_acc.id if default_acc else None
        created = 0
        skipped_dup = 0
        for i, c in enumerate(candidates):
            if request.form.get(f"skip_{i}") == "1":
                continue
            if c.get("duplicate"):
                skipped_dup += 1
                continue
            expense_id = request.form.get(f"expense_account_id_{i}", type=int)
            credit_id = request.form.get(f"credit_account_id_{i}", type=int) or default_credit_id
            if not expense_id or not credit_id:
                continue
            trans_date = datetime.strptime(c["date"], "%Y-%m-%d").date()
            if is_duplicate(trans_date, c["amount"], c.get("payee") or ""):
                skipped_dup += 1
                continue
            t = Transaction(
                transaction_type="expense",
                date=trans_date,
                amount=c["amount"],
                debit_account_id=expense_id,
                credit_account_id=credit_id,
                payee=c.get("payee"),
                description=f"CSV取込: {c.get('payee') or ''}"[:512],
                payment_method="transfer",
                recurring_expense_id=None,
            )
            db.session.add(t)
            created += 1
        db.session.commit()
        session.pop("csv_import_candidates", None)
        return redirect(url_for("transactions.list_transactions") + f"?imported={created}&skipped_dup={skipped_dup}")

    asset_accounts = get_asset_accounts()
    expense_accounts = get_expense_accounts()
    return render_template(
        "csv_import/preview.html",
        candidates=candidates,
        asset_accounts=asset_accounts,
        expense_accounts=expense_accounts,
    )


@bp.route("/cancel", methods=["POST"])
def cancel():
    session.pop("csv_import_candidates", None)
    return redirect(url_for("transactions.list_transactions"))


# ---------- Google Drive から CSV 取込 ----------
@bp.route("/from-drive", methods=["GET", "POST"])
def from_drive():
    """ドライブのフォルダIDを入力してファイル一覧を表示し、選択したCSVを取込に渡す。"""
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return render_template("csv_import/from_drive.html", drive_available=False)
    try:
        from drive_service import get_drive_service, is_connected, list_files_in_folder, get_file_content
    except ImportError:
        return render_template("csv_import/from_drive.html", drive_available=False)
    if not is_connected(_get_setting):
        return render_template("csv_import/from_drive.html", drive_available=True, drive_connected=False)

    if request.method == "GET":
        folder_id = request.args.get("folder_id", "").strip()
        # URLを貼った場合は folders/ の直後をIDとして抽出
        if folder_id and ("folders/" in folder_id or "drive.google.com" in folder_id):
            for sep in ("folders/", "/folders/"):
                if sep in folder_id:
                    folder_id = folder_id.split(sep)[-1].split("/")[0].split("?")[0]
                    break
        if not folder_id:
            return render_template("csv_import/from_drive.html", drive_available=True, drive_connected=True)
        service = get_drive_service(_get_setting)
        if not service:
            return render_template("csv_import/from_drive.html", drive_available=True, drive_connected=True, error="Drive に接続できません")
        try:
            files = list_files_in_folder(service, folder_id)
            # CSV らしいファイルを優先表示（.csv または text/csv）
            csv_files = [f for f in files if f.get("name", "").lower().endswith(".csv") or f.get("mimeType") == "text/csv"]
            other_files = [f for f in files if f not in csv_files]
            return render_template(
                "csv_import/from_drive.html",
                drive_available=True,
                drive_connected=True,
                folder_id=folder_id,
                csv_files=csv_files,
                other_files=other_files,
            )
        except Exception as e:
            return render_template(
                "csv_import/from_drive.html",
                drive_available=True,
                drive_connected=True,
                folder_id=folder_id,
                csv_files=[],
                other_files=[],
                error=f"フォルダの取得に失敗しました: {e}",
            )

    folder_id = request.form.get("folder_id", "").strip()
    if not folder_id:
        return redirect(url_for("csv_import.from_drive"))
    return redirect(url_for("csv_import.from_drive", folder_id=folder_id))


@bp.route("/from-drive/pick")
def from_drive_pick():
    """指定した Drive ファイルをダウンロードし、取込画面に渡す。"""
    file_id = request.args.get("file_id")
    filename = request.args.get("filename", "import.csv")
    if not file_id:
        return redirect(url_for("csv_import.from_drive"))
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return redirect(url_for("csv_import.upload"))
    try:
        from drive_service import get_drive_service, is_connected, get_file_content
    except ImportError:
        return redirect(url_for("csv_import.upload"))
    if not is_connected(_get_setting):
        return redirect(url_for("csv_import.upload"))
    service = get_drive_service(_get_setting)
    if not service:
        return redirect(url_for("csv_import.upload"))
    try:
        raw = get_file_content(service, file_id)
        if raw.startswith(b"\xef\xbb\xbf"):
            text = raw.decode("utf-8-sig")
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp932")
    except Exception:
        return redirect(url_for("csv_import.from_drive") + "?error=download")
    session["csv_import_drive_content"] = text
    session["csv_import_drive_filename"] = filename or "import.csv"
    return redirect(url_for("csv_import.upload"))
