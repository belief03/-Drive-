# -*- coding: utf-8 -*-
"""DBモデル。勘定科目・取引・設定など。"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index

db = SQLAlchemy()


class Account(db.Model):
    """勘定科目マスタ。"""
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)  # 科目コード（110, 120 等）
    name = db.Column(db.String(64), nullable=False)
    category = db.Column(db.String(32), nullable=False)  # asset, liability, equity, revenue, expense, owner
    is_common_expense = db.Column(db.Boolean, default=False)  # 「よくある経費」に表示するか
    common_expense_order = db.Column(db.Integer, default=0)  # よくある経費の表示順
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "is_common_expense": self.is_common_expense,
            "common_expense_order": self.common_expense_order,
        }


class Transaction(db.Model):
    """取引（仕訳）。1取引＝1行で、借方・貸方の2行で1仕訳とする場合もあるが、
    ここでは1行＝1仕訳（借方科目・貸方科目・金額を1行で持つ）とする。
    複式簿記では1取引につき借方と貸方の2行が必要なので、同じ transaction_group_id で2行作る方式も可。
    シンプルにするため、1行で「取引」を表し、debit_account_id / credit_account_id / amount で持つ。
    """
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(32), nullable=False)  # sales, misc_income, expense, transfer, loan, owner, other
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # 円
    debit_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    payee = db.Column(db.String(256))  # 取引先（任意）。提案・アラートに使用
    description = db.Column(db.String(512))  # 摘要
    payment_method = db.Column(db.String(32))  # cash, transfer, credit, qr（経費の場合）
    qr_source = db.Column(db.String(32))  # bank, credit（QR決済時の引き落とし元）
    receipt_kept = db.Column(db.Boolean, default=False)  # 領収書保管済
    receipt_memo = db.Column(db.String(256))  # 領収書の保管場所など
    receipt_path = db.Column(db.String(512), nullable=True)  # 領収書画像の相対パス（instance 内）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 固定費から自動作成された取引の紐づけ（二重反映防止用）
    recurring_expense_id = db.Column(db.Integer, db.ForeignKey("recurring_expenses.id"), nullable=True)
    # 将来の複数ユーザー用
    user_id = db.Column(db.Integer, nullable=True)

    debit_account = db.relationship("Account", foreign_keys=[debit_account_id])
    credit_account = db.relationship("Account", foreign_keys=[credit_account_id])

    __table_args__ = (Index("ix_transactions_date", "date"), Index("ix_transactions_payee", "payee"),)

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_type": self.transaction_type,
            "date": self.date.isoformat() if self.date else None,
            "amount": self.amount,
            "debit_account_id": self.debit_account_id,
            "credit_account_id": self.credit_account_id,
            "payee": self.payee,
            "description": self.description,
            "payment_method": self.payment_method,
            "qr_source": self.qr_source,
            "receipt_kept": self.receipt_kept,
            "receipt_memo": self.receipt_memo,
            "receipt_path": self.receipt_path,
        }


class RecurringExpense(db.Model):
    """毎月自動反映する固定費のテンプレート。"""
    __tablename__ = "recurring_expenses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)  # 例: 通信費・家賃
    amount = db.Column(db.Integer, nullable=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)  # 経費科目
    credit_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)  # 支払方法（口座）
    payee = db.Column(db.String(256))  # 取引先（任意）
    description = db.Column(db.String(512))  # 摘要（任意）
    day_of_month = db.Column(db.Integer, nullable=False, default=1)  # 毎月の何日付で計上するか（1〜28推奨）
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    debit_account = db.relationship("Account", foreign_keys=[debit_account_id])
    credit_account = db.relationship("Account", foreign_keys=[credit_account_id])


class Setting(db.Model):
    """設定（業種など）。キー・値で保存。"""
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Industry(db.Model):
    """業種マスタ（法改正・追加時にDBで管理）。"""
    __tablename__ = "industries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
