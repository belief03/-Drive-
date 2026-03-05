# -*- coding: utf-8 -*-
"""固定費（毎月自動反映）の登録・反映。"""
from datetime import date
from calendar import monthrange
from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Account, Transaction, RecurringExpense, Setting

bp = Blueprint("recurring", __name__)


def get_asset_accounts():
    return Account.query.filter_by(category="asset", is_active=True).order_by(Account.code).all()


def get_expense_accounts():
    return Account.query.filter_by(category="expense", is_active=True).order_by(
        Account.common_expense_order, Account.code
    ).all()


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        amount = request.form.get("amount", type=int) or 0
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)
        payee = request.form.get("payee", "").strip() or None
        description = request.form.get("description", "").strip() or None
        day_of_month = min(28, max(1, request.form.get("day_of_month", type=int) or 1))
        if name and debit_id and credit_id and amount > 0:
            r = RecurringExpense(
                name=name,
                amount=amount,
                debit_account_id=debit_id,
                credit_account_id=credit_id,
                payee=payee,
                description=description,
                day_of_month=day_of_month,
            )
            db.session.add(r)
            db.session.commit()
            return redirect(url_for("recurring.index"))
    asset_accounts = get_asset_accounts()
    expense_accounts = get_expense_accounts()
    return render_template(
        "recurring/form.html",
        item=None,
        asset_accounts=asset_accounts,
        expense_accounts=expense_accounts,
    )


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit(id):
    item = RecurringExpense.query.get_or_404(id)
    if request.method == "POST":
        item.name = request.form.get("name", "").strip() or item.name
        item.amount = request.form.get("amount", type=int) or item.amount
        debit_id = request.form.get("debit_account_id", type=int)
        credit_id = request.form.get("credit_account_id", type=int)
        if debit_id:
            item.debit_account_id = debit_id
        if credit_id:
            item.credit_account_id = credit_id
        item.payee = request.form.get("payee", "").strip() or None
        item.description = request.form.get("description", "").strip() or None
        item.day_of_month = min(28, max(1, request.form.get("day_of_month", type=int) or 1))
        item.is_active = request.form.get("is_active") == "1"
        db.session.commit()
        return redirect(url_for("recurring.index"))
    asset_accounts = get_asset_accounts()
    expense_accounts = get_expense_accounts()
    return render_template(
        "recurring/form.html",
        item=item,
        asset_accounts=asset_accounts,
        expense_accounts=expense_accounts,
    )


@bp.route("/<int:id>/delete", methods=["POST"])
def delete(id):
    item = RecurringExpense.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("recurring.index"))


def _last_day_of_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def apply_recurring_for_month(year: int, month: int):
    """指定年月の固定費を取引として一括登録。作成した件数を返す。"""
    items = RecurringExpense.query.filter_by(is_active=True).all()
    created = 0
    for r in items:
        day = min(r.day_of_month, _last_day_of_month(year, month))
        trans_date = date(year, month, day)
        start = date(year, month, 1)
        end = date(year, month, _last_day_of_month(year, month))
        exists = Transaction.query.filter(
            Transaction.recurring_expense_id == r.id,
            Transaction.date >= start,
            Transaction.date <= end,
        ).first()
        if exists:
            continue
        t = Transaction(
            transaction_type="expense",
            date=trans_date,
            amount=r.amount,
            debit_account_id=r.debit_account_id,
            credit_account_id=r.credit_account_id,
            payee=r.payee,
            description=r.description or f"固定費: {r.name}",
            payment_method="transfer",
            recurring_expense_id=r.id,
        )
        db.session.add(t)
        created += 1
    db.session.commit()
    return created


def _get_setting(key: str, default: str = "") -> str:
    s = Setting.query.filter_by(key=key).first()
    if s is None or s.value is None:
        return default.strip() if isinstance(default, str) else ""
    return (s.value or default).strip()


def _set_setting(key: str, value: str):
    s = Setting.query.filter_by(key=key).first()
    if s:
        s.value = value
    else:
        s = Setting(key=key, value=value)
        db.session.add(s)
    db.session.commit()


@bp.route("/")
def index():
    # 自動反映: 設定ONかつ今月が未反映なら反映してから一覧へ（リダイレクト後の再実行は行わない）
    if (
        request.args.get("auto_applied") is None
        and _get_setting("auto_apply_recurring") == "1"
    ):
        today = date.today()
        current_ym = f"{today.year}-{today.month:02d}"
        last_ym = _get_setting("last_auto_applied_recurring")
        if last_ym != current_ym:
            try:
                created = apply_recurring_for_month(today.year, today.month)
                _set_setting("last_auto_applied_recurring", current_ym)
                return redirect(
                    url_for("recurring.index", auto_applied=created, year=today.year, month=today.month)
                )
            except Exception:
                db.session.rollback()
                raise
    items = RecurringExpense.query.order_by(RecurringExpense.day_of_month).all()
    return render_template("recurring/index.html", items=items)


@bp.route("/apply", methods=["GET", "POST"])
def apply():
    """指定月の固定費を取引として一括登録。"""
    if request.method == "POST":
        year = request.form.get("year", type=int) or date.today().year
        month = request.form.get("month", type=int) or date.today().month
        created = apply_recurring_for_month(year, month)
        return redirect(url_for("recurring.index") + f"?applied={created}&year={year}&month={month}")
    return render_template("recurring/apply.html", now=date.today())

