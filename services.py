# -*- coding: utf-8 -*-
"""ビジネスロジック：勘定科目提案・同一取引先チェックなど。"""
from models import db, Account, Transaction


def get_expense_account_suggestion(payee: str) -> dict:
    """
    取引先から経費の勘定科目を提案（リード型）。
    同一取引先の過去の取引で最も使われている勘定科目を返す。
    """
    if not payee or not payee.strip():
        return {"suggested_account": None, "message": None, "past_count": 0}
    payee = payee.strip()
    # 経費取引で同じ取引先の過去の仕訳を集計（貸方ではなく借方＝経費科目で集計）
    from sqlalchemy import func
    past = (
        db.session.query(Transaction.debit_account_id, func.count(Transaction.id).label("cnt"))
        .filter(
            Transaction.transaction_type == "expense",
            Transaction.payee.ilike(f"%{payee}%"),
        )
        .group_by(Transaction.debit_account_id)
        .order_by(func.count(Transaction.id).desc())
        .first()
    )
    if not past:
        return {"suggested_account": None, "message": None, "past_count": 0}
    acc = Account.query.get(past.debit_account_id)
    if not acc:
        return {"suggested_account": None, "message": None, "past_count": 0}
    return {
        "suggested_account": acc.to_dict(),
        "message": f"取引先「{payee}」の過去{past.cnt}件は「{acc.name}」で計上しています。",
        "past_count": past.cnt,
    }


def check_expense_account_consistency(payee: str, chosen_account_id: int) -> dict:
    """
    経費で選択した勘定科目が、同一取引先の過去と一致するかチェック。
    一致しない場合はアラート用メッセージと過去の科目を返す。
    """
    if not payee or not payee.strip():
        return {"consistent": True, "alert": None, "past_account": None}
    payee = payee.strip()
    from sqlalchemy import func
    past = (
        db.session.query(Transaction.debit_account_id, func.count(Transaction.id).label("cnt"))
        .filter(
            Transaction.transaction_type == "expense",
            Transaction.payee.ilike(f"%{payee}%"),
        )
        .group_by(Transaction.debit_account_id)
        .order_by(func.count(Transaction.id).desc())
        .first()
    )
    if not past or past.debit_account_id == chosen_account_id:
        return {"consistent": True, "alert": None, "past_account": None}
    past_acc = Account.query.get(past.debit_account_id)
    return {
        "consistent": False,
        "alert": f"この取引先の過去{past.cnt}件は「{past_acc.name}」で計上しています。科目を統一することをおすすめします。",
        "past_account": past_acc.to_dict() if past_acc else None,
    }
