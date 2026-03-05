# -*- coding: utf-8 -*-
"""Google Drive API 連携：OAuth とファイルアップロード。"""
import json
import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)

# ローカル開発で http://127.0.0.1 等を使う場合に必要。本番で HTTPS を使う場合は環境変数で 0 にできる。
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


# アプリ作成ファイルのみ + ユーザー指定フォルダの読み取り（Drive→本システム取込用）+ スプレッドシート作成・編集
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]
SETTING_CREDENTIALS = "google_drive_credentials"
SETTING_FOLDER_ID = "google_drive_backup_folder_id"


def _credentials_from_setting(get_setting_func):
    """Setting に保存した credentials JSON から Credentials を復元。"""
    raw = get_setting_func(SETTING_CREDENTIALS)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def credentials_to_dict(creds):
    return {
        "token": creds.token,
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


def get_flow(client_id, client_secret, redirect_uri):
    """OAuth 2.0 Flow を生成。"""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


def get_authorization_url(flow):
    """認可URLとstateを返す。(auth_url, state)"""
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def save_credentials_from_code(flow, code, set_setting_func, authorization_response=None):
    """認可コードをトークンに交換し、Setting に保存。"""
    if authorization_response:
        flow.fetch_token(authorization_response=authorization_response)
    else:
        flow.fetch_token(code=code)
    creds = flow.credentials
    set_setting_func(SETTING_CREDENTIALS, json.dumps(credentials_to_dict(creds)))
    return True


def _refresh_creds_if_needed(creds, set_setting_func):
    """トークン切れなら更新して保存。"""
    if creds and creds.expired and getattr(creds, "refresh_token", None):
        creds.refresh(Request())
        if set_setting_func:
            set_setting_func(SETTING_CREDENTIALS, json.dumps(credentials_to_dict(creds)))
    return creds


def get_drive_service(get_setting_func, set_setting_func=None):
    """保存済み credentials で Drive API サービスを取得。トークン切れなら更新して保存。"""
    creds = _credentials_from_setting(get_setting_func)
    if not creds:
        return None
    creds = _refresh_creds_if_needed(creds, set_setting_func)
    return build("drive", "v3", credentials=creds)


def get_sheets_service(get_setting_func, set_setting_func=None):
    """保存済み credentials で Google Sheets API サービスを取得。スプレッドシート作成・編集に必要。"""
    creds = _credentials_from_setting(get_setting_func)
    if not creds:
        return None
    creds = _refresh_creds_if_needed(creds, set_setting_func)
    return build("sheets", "v4", credentials=creds)


def is_connected(get_setting_func):
    """連携済みか。"""
    return bool(get_setting_func(SETTING_CREDENTIALS))


def disconnect(set_setting_func):
    """連携解除：保存した credentials とフォルダID を削除。"""
    set_setting_func(SETTING_CREDENTIALS, "")
    set_setting_func(SETTING_FOLDER_ID, "")


def ensure_backup_folder(service, folder_name="帳簿バックアップ"):
    """ドライブにフォルダがなければ作成し、フォルダIDを返す。"""
    q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    resp = service.files().list(q=q, spaces="drive", fields="files(id, name)").execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_file(service, folder_id, file_content, filename, mime_type="application/octet-stream"):
    """指定フォルダにファイルをアップロード。content は bytes または BytesIO。"""
    if isinstance(file_content, bytes):
        file_content = BytesIO(file_content)
    meta = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(file_content, mimetype=mime_type, resumable=True)
    f = service.files().create(body=meta, media_body=media, fields="id").execute()
    return f.get("id")


def list_files_in_folder(service, folder_id, mime_type_filter=None):
    """指定フォルダ内のファイル一覧。mime_type_filter 例: 'text/csv' または 'application/vnd.google-apps.folder'。"""
    q = f"'{folder_id}' in parents and trashed = false"
    if mime_type_filter:
        q += f" and mimeType = '{mime_type_filter}'"
    resp = service.files().list(
        q=q, spaces="drive", fields="files(id, name, mimeType)", orderBy="name"
    ).execute()
    return resp.get("files", [])


def get_file_content(service, file_id):
    """ファイルの内容を bytes で取得。"""
    request = service.files().get_media(fileId=file_id)
    buf = BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    return buf.read()


def create_spreadsheet_with_values(sheets_service, title, rows):
    """
    新規スプレッドシートを作成し、先頭シートに rows（リストのリスト）を書き込む。
    戻り値: (spreadsheet_id, spreadsheet_url, error_hint) のタプル。
    error_hint: 失敗時のみ。'api_disabled' | 'quota' | 'scope' | None（汎用）
    """
    if not sheets_service or not rows:
        return None, None, None
    try:
        spreadsheet = (
            sheets_service.spreadsheets()
            .create(
                body={"properties": {"title": title}},
                fields="spreadsheetId,spreadsheetUrl,sheets(properties(title))",
            )
            .execute()
        )
        sid = spreadsheet.get("spreadsheetId")
        url = spreadsheet.get("spreadsheetUrl")
        if not sid:
            return None, None, None
        # 先頭シートの実際の名前を取得（言語設定で "シート1" 等になるため "Sheet1" 固定は不可）
        sheets_list = spreadsheet.get("sheets") or []
        sheet_title = "Sheet1"
        if sheets_list:
            sheet_title = (sheets_list[0].get("properties") or {}).get("title") or sheet_title
        escaped_title = sheet_title.replace("'", "''")
        range_a1 = f"'{escaped_title}'!A1"
        sheets_service.spreadsheets().values().update(
            spreadsheetId=sid,
            range=range_a1,
            body={"values": rows},
            valueInputOption="USER_ENTERED",
        ).execute()
        return sid, url, None
    except Exception as e:
        err_str = str(e).lower()
        if "403" in err_str or "forbidden" in err_str:
            if "sheets" in err_str or "spreadsheet" in err_str or "has not been used" in err_str:
                hint = "api_disabled"
            else:
                hint = "scope"
        elif "429" in err_str or "quota" in err_str or "rate" in err_str:
            hint = "quota"
        else:
            hint = None
        logger.exception(
            "Google Sheets create failed: %s (hint=%s). Enable Sheets API and ensure spreadsheets scope is granted.",
            e, hint,
        )
        return None, None, hint
