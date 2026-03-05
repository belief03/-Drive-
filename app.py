# -*- coding: utf-8 -*-
"""青色申告用帳簿ツール - Flask エントリポイント。"""
import os
from flask import Flask, request, redirect, render_template
from config import Config
from models import db
from database import init_db

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    init_db(app)

    @app.errorhandler(404)
    def not_found(e):
        """404 のときの案内ページ。"""
        return render_template("errors/404.html"), 404

    @app.before_request
    def redirect_localhost_to_127():
        """localhost で開かれた場合は 127.0.0.1 にリダイレクトし、Google連携時のセッション不一致を防ぐ。"""
        host = request.host or ""
        if host.startswith("localhost"):
            # 同じパス・クエリで 127.0.0.1 に振り向ける（1回だけ置換）
            new_url = request.url.replace("localhost", "127.0.0.1", 1)
            return redirect(new_url, code=302)

    from routes import main, transactions, settings_bp, reports, hints, recurring, knowledge, csv_import
    app.register_blueprint(main.bp)
    app.register_blueprint(transactions.bp, url_prefix="/transactions")
    app.register_blueprint(csv_import.bp)
    app.register_blueprint(settings_bp.bp, url_prefix="/settings")
    app.register_blueprint(reports.bp, url_prefix="/reports")
    app.register_blueprint(hints.bp, url_prefix="/hints")
    app.register_blueprint(recurring.bp, url_prefix="/recurring")
    app.register_blueprint(knowledge.bp, url_prefix="/knowledge")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
