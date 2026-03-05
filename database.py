# -*- coding: utf-8 -*-
"""DB初期化と勘定科目・業種のシードデータ。"""
import os
from models import db, Account, Setting, Industry

# 勘定科目シード（設計ドキュメントに基づく）
ACCOUNTS_SEED = [
    # 資産
    ("110", "現金", "asset", False, 0),
    ("120", "普通預金", "asset", False, 0),
    ("130", "売掛金", "asset", False, 0),
    ("140", "前払金", "asset", False, 0),
    ("150", "未収金", "asset", False, 0),
    ("160", "仮払金", "asset", False, 0),
    ("170", "貸付金", "asset", False, 0),
    ("210", "建物", "asset", False, 0),
    ("220", "車両運搬具", "asset", False, 0),
    ("230", "工具器具備品", "asset", False, 0),
    ("240", "ソフトウェア", "asset", False, 0),
    ("290", "その他資産", "asset", False, 0),
    # 負債
    ("310", "買掛金", "liability", False, 0),
    ("320", "借入金", "liability", False, 0),
    ("330", "未払金", "liability", False, 0),
    ("340", "預り金", "liability", False, 0),
    ("390", "その他負債", "liability", False, 0),
    # 純資産
    ("410", "元入金", "equity", False, 0),
    ("420", "繰越利益剰余金", "equity", False, 0),
    # 収益
    ("510", "売上", "revenue", False, 0),
    ("520", "雑収入", "revenue", False, 0),
    ("530", "受取利息", "revenue", False, 0),
    # 費用（よくある経費の表示順: 交通費, 通信費, 地代家賃, 消耗品費, 接待交際費, 支払手数料, 水道光熱費, 外注費, 広告宣伝費, その他）
    ("610", "租税公課", "expense", False, 0),
    ("620", "荷造運賃", "expense", False, 0),
    ("625", "地代家賃", "expense", True, 3),
    ("630", "水道光熱費", "expense", True, 7),
    ("640", "旅費交通費", "expense", True, 1),
    ("650", "通信費", "expense", True, 2),
    ("660", "広告宣伝費", "expense", True, 9),
    ("670", "接待交際費", "expense", True, 5),
    ("680", "損害保険料", "expense", False, 0),
    ("690", "修繕費", "expense", False, 0),
    ("700", "消耗品費", "expense", True, 4),
    ("710", "減価償却費", "expense", False, 0),
    ("720", "福利厚生費", "expense", False, 0),
    ("730", "給料賃金", "expense", False, 0),
    ("740", "外注費", "expense", True, 8),
    ("750", "利子割引料", "expense", False, 0),
    ("760", "支払手数料", "expense", True, 6),
    ("790", "その他", "expense", True, 10),
    # 事業主
    ("810", "事業主貸", "owner", False, 0),
    ("820", "事業主借", "owner", False, 0),
]

INDUSTRIES_SEED = [
    "IT・Web受託",
    "コンサル",
    "物販",
    "飲食",
    "士業",
    "その他",
]


def init_db(app):
    """DB作成とテーブル作成。"""
    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if uri.startswith("sqlite:///"):
            db_dir = os.path.dirname(uri.replace("sqlite:///", ""))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        db.create_all()
        if Account.query.first() is None:
            for code, name, category, is_common, order in ACCOUNTS_SEED:
                db.session.add(Account(
                    code=code,
                    name=name,
                    category=category,
                    is_common_expense=is_common,
                    common_expense_order=order,
                ))
            db.session.commit()
        if Industry.query.first() is None:
            for i, name in enumerate(INDUSTRIES_SEED):
                db.session.add(Industry(name=name, display_order=i))
            db.session.commit()
        # 既存DBに地代家賃がなければ追加（法改正・科目追加の例）
        if Account.query.filter_by(code="625").first() is None:
            db.session.add(Account(
                code="625",
                name="地代家賃",
                category="expense",
                is_common_expense=True,
                common_expense_order=3,
            ))
            db.session.commit()
        # 既存DBに recurring_expense_id カラムがなければ追加
        from sqlalchemy import text
        conn = db.session.connection()
        try:
            r = conn.execute(text("PRAGMA table_info(transactions)"))
            cols = [row[1] for row in r]
            if "recurring_expense_id" not in cols:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN recurring_expense_id INTEGER REFERENCES recurring_expenses(id)"))
                db.session.commit()
            if "receipt_path" not in cols:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN receipt_path VARCHAR(512)"))
                db.session.commit()
        except Exception:
            db.session.rollback()
