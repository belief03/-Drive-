# -*- coding: utf-8 -*-
"""
固定費を指定月（または今月）に反映するスクリプト。
毎月1日などに cron / タスクスケジューラ で実行すると、手動で画面を開かずに固定費を自動反映できます。

使い方:
  python scripts/apply_recurring.py              # 今月分を反映
  python scripts/apply_recurring.py 2025 3      # 2025年3月分を反映
"""
import sys
import os
from datetime import date

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from routes.recurring import apply_recurring_for_month


def main():
    if len(sys.argv) >= 3:
        try:
            year = int(sys.argv[1])
            month = int(sys.argv[2])
            if not (1 <= month <= 12):
                print("月は 1〜12 を指定してください。", file=sys.stderr)
                sys.exit(1)
        except ValueError:
            print("年・月は整数で指定してください。例: python scripts/apply_recurring.py 2025 3", file=sys.stderr)
            sys.exit(1)
    else:
        today = date.today()
        year, month = today.year, today.month

    with app.app_context():
        n = apply_recurring_for_month(year, month)
    print(f"固定費を {year}年{month}月 に {n} 件反映しました。")


if __name__ == "__main__":
    main()
