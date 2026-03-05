# -*- coding: utf-8 -*-
import logging
import os
from datetime import date
from urllib.parse import quote
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from models import db, Setting, Industry

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)


def _read_drive_credential_from_instance(filename):
    """instance フォルダ内のテキストファイル1行目を返す（設定画面表示時に再読み込み用）。"""
    try:
        path = os.path.join(current_app.instance_path, filename)
        if not os.path.isfile(path):
            return ""
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                with open(path, "r", encoding=enc) as f:
                    return (f.readline() or "").strip()
            except (UnicodeDecodeError, UnicodeError):
                continue
    except Exception:
        pass
    return ""


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
    try:
        industry = Setting.query.filter_by(key="industry").first()
        current = industry.value if industry else None
        industries = Industry.query.filter_by(is_active=True).order_by(Industry.display_order).all()
        auto_apply_recurring = _get_setting("auto_apply_recurring", "0") == "1"
        # 環境変数または config で有効でない場合、instance フォルダのファイルを表示時に再読み込み
        drive_enabled = bool(current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"))
        if not drive_enabled:
            cid = _read_drive_credential_from_instance("google_drive_client_id.txt")
            secret = _read_drive_credential_from_instance("google_drive_client_secret.txt")
            if cid and secret:
                drive_enabled = True
                current_app.config["GOOGLE_DRIVE_CLIENT_ID"] = cid
                current_app.config["GOOGLE_DRIVE_CLIENT_SECRET"] = secret
        drive_connected = False
        drive_redirect_uri = ""
        if drive_enabled:
            try:
                from drive_service import is_connected
                drive_connected = is_connected(_get_setting)
                drive_redirect_uri = _drive_redirect_uri()
            except Exception as e:
                logger.warning("Settings: drive status check failed: %s", e, exc_info=True)
        current_year = date.today().year
        return render_template(
            "settings/index.html",
            industries=industries,
            current=current,
            auto_apply_recurring=auto_apply_recurring,
            drive_enabled=drive_enabled,
            drive_connected=drive_connected,
            drive_redirect_uri=drive_redirect_uri,
            current_year=current_year,
            settings_error=None,
        )
    except Exception as e:
        logger.exception("Settings index failed")
        return render_template(
            "settings/index.html",
            industries=[],
            current=None,
            auto_apply_recurring=False,
            drive_enabled=False,
            drive_connected=False,
            drive_redirect_uri="",
            current_year=date.today().year,
            settings_error=str(e),
        )


@bp.route("/industry", methods=["POST"])
def update_industry():
    value = request.form.get("industry", "").strip()
    s = Setting.query.filter_by(key="industry").first()
    if s:
        s.value = value
    else:
        s = Setting(key="industry", value=value)
        db.session.add(s)
    db.session.commit()
    return redirect(url_for("settings.index"))


@bp.route("/auto_apply_recurring", methods=["POST"])
def update_auto_apply_recurring():
    value = "1" if request.form.get("auto_apply_recurring") == "1" else "0"
    s = Setting.query.filter_by(key="auto_apply_recurring").first()
    if s:
        s.value = value
    else:
        s = Setting(key="auto_apply_recurring", value=value)
        db.session.add(s)
    db.session.commit()
    return redirect(url_for("settings.index"))


# ---------- Google Drive 連携 ----------
def _drive_redirect_uri():
    """現在のリクエストのホストでコールバックURLを組み立てる。セッションとコールバックのホストを一致させる。"""
    base = current_app.config.get("GOOGLE_DRIVE_REDIRECT_URI")
    if base:
        return base.rstrip("/")
    root = request.url_root.rstrip("/")
    return f"{root}/settings/drive/callback"


@bp.route("/drive/connect")
def drive_connect():
    """Google 認可画面へリダイレクト。"""
    cid = current_app.config.get("GOOGLE_DRIVE_CLIENT_ID")
    secret = current_app.config.get("GOOGLE_DRIVE_CLIENT_SECRET")
    redirect_uri = _drive_redirect_uri()
    if not cid or not secret:
        return redirect(url_for("settings.index") + "?drive=no_config")
    try:
        from drive_service import get_flow, get_authorization_url
        flow = get_flow(cid, secret, redirect_uri)
        auth_url, state = get_authorization_url(flow)
        session["google_drive_flow_state"] = state
        session["google_drive_flow_redirect_uri"] = redirect_uri
        return redirect(auth_url)
    except Exception as e:
        err_msg = str(e)[:300]
        logger.exception("Google Drive 連携開始に失敗: %s (redirect_uri=%s)", e, redirect_uri)
        return redirect(
            url_for("settings.index") + "?drive=error&msg=" + quote(err_msg, safe="")
        )


@bp.route("/drive/callback")
def drive_callback():
    """OAuth コールバック。認可コードをトークンに交換して保存。"""
    code = request.args.get("code")
    state = request.args.get("state")
    saved_state = session.get("google_drive_flow_state")

    if not code:
        logger.warning("Google Drive callback: code is missing (user may have refreshed or bookmarked callback URL)")
        return redirect(url_for("settings.index") + "?drive=callback_failed&reason=no_code")
    if state != saved_state:
        logger.warning(
            "Google Drive callback: state mismatch. session_state=%s, url_state=%s. "
            "Often caused by opening app via localhost but redirect_uri is 127.0.0.1 (or vice versa).",
            saved_state, state,
        )
        return redirect(url_for("settings.index") + "?drive=callback_failed&reason=session")
    session.pop("google_drive_flow_state", None)
    session.pop("google_drive_flow_redirect_uri", None)
    # トークン交換では「今コールバックが届いているURL」を redirect_uri に使う（Google がリダイレクトした先と一致させる）
    redirect_uri = request.base_url
    cid = current_app.config.get("GOOGLE_DRIVE_CLIENT_ID")
    secret = current_app.config.get("GOOGLE_DRIVE_CLIENT_SECRET")
    if not cid or not secret:
        return redirect(url_for("settings.index") + "?drive=no_config")
    try:
        from drive_service import get_flow, save_credentials_from_code
        flow = get_flow(cid, secret, redirect_uri)
        flow.redirect_uri = redirect_uri
        save_credentials_from_code(flow, None, _set_setting, authorization_response=request.url)
        return redirect(url_for("settings.index") + "?drive=connected")
    except Exception as e:
        err_msg = str(e)[:300]
        err_lower = err_msg.lower()
        logger.exception(
            "Google Drive token exchange failed: %s (redirect_uri used: %s)",
            e, redirect_uri,
        )
        if "redirect_uri_mismatch" in err_lower or "redirect_uri" in err_lower:
            reason = "redirect_uri"
        elif "invalid_grant" in err_lower or "invalid_request" in err_lower:
            reason = "invalid_grant"
        else:
            reason = "token"
        url = url_for("settings.index") + f"?drive=callback_failed&reason={reason}"
        if err_msg:
            url += "&msg=" + quote(err_msg, safe="")
        return redirect(url)


@bp.route("/drive/disconnect", methods=["POST"])
def drive_disconnect():
    """連携解除。"""
    try:
        from drive_service import disconnect
        disconnect(_set_setting)
    except Exception:
        pass
    return redirect(url_for("settings.index"))


@bp.route("/drive/backup", methods=["POST"])
def drive_backup():
    """指定年のCSVと領収書まとめPDFをドライブの「帳簿バックアップ」フォルダにアップロード。"""
    if not current_app.config.get("GOOGLE_DRIVE_CLIENT_ID"):
        return redirect(url_for("settings.index") + "?drive=no_config")
    try:
        from drive_service import get_drive_service, is_connected, ensure_backup_folder, upload_file
        if not is_connected(_get_setting):
            return redirect(url_for("settings.index") + "?drive=not_connected")
        service = get_drive_service(_get_setting, _set_setting)
        if not service:
            return redirect(url_for("settings.index") + "?drive=not_connected")
        folder_id = ensure_backup_folder(service)
        from datetime import datetime
        today = date.today()
        prefix = today.isoformat()

        # CSV エクスポート（当年）
        year = request.form.get("year", type=int) or today.year
        from routes.reports import export_csv_content
        csv_content = export_csv_content(year)
        if csv_content:
            upload_file(service, folder_id, csv_content, f"{prefix}_transactions_{year}.csv", "text/csv")

        # 領収書まとめPDF（当年・通年）
        from routes.reports import build_receipts_pdf_bytes
        pdf_content = build_receipts_pdf_bytes(year, None)
        if pdf_content:
            upload_file(service, folder_id, pdf_content, f"{prefix}_receipts_{year}.pdf", "application/pdf")

        return redirect(url_for("settings.index") + "?drive=backup_ok")
    except Exception as e:
        return redirect(url_for("settings.index") + f"?drive=backup_failed&msg={str(e)[:50]}")
