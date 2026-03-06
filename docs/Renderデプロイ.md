# Render へのデプロイ手順

試運用・コスト抑制を目的に、青色申告帳簿ツールを **Render** で公開する手順です。正式運用時に Heroku 等へ移行する想定です。

---

## 前提

- GitHub にリポジトリがプッシュ済みであること
- [Render](https://render.com) のアカウント（GitHub 連携で無料登録可）

---

## 1. Render で Web サービスを作成

1. [Render Dashboard](https://dashboard.render.com) にログインし、**New** → **Web Service** を選択
2. 接続する **GitHub リポジトリ**を選び、**Connect**
3. 次のように設定する

| 項目 | 値 |
|------|-----|
| **Name** | 任意（例: `account-book`） |
| **Region** | お好み（Singapore など） |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | **必ず** `gunicorn wsgi:application` に変更する（デフォルトの `gunicorn your_application.wsgi` のままにしない） |
| **Instance Type** | **Free**（スリープあり） or **Starter**（$7/月・常時起動） |

4. **Advanced** を開き、必要なら **Environment Variables** を追加（後述）

**重要**: Start Command を変更していないと、起動時に `ModuleNotFoundError: 'your_application' という名前のモジュールがありません` が出ます。必ず上記のとおり設定してください。

---

## 2. 環境変数

**Environment** で以下を設定する。

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `SECRET_KEY` | ○ | 本番用の秘密鍵（例: `python -c "import secrets; print(secrets.token_hex(32))"` で生成） |
| `DATABASE_URL` | ○（本番） | PostgreSQL の接続 URL（下記「データベース」参照） |
| `GOOGLE_DRIVE_CLIENT_ID` | 任意 | Google 連携を使う場合 |
| `GOOGLE_DRIVE_CLIENT_SECRET` | 任意 | 同上 |
| `GOOGLE_DRIVE_REDIRECT_URI` | 任意 | 例: `https://＜サービス名＞.onrender.com/settings/drive/callback` |

- **SECRET_KEY** は必ず本番用のランダム文字列にすること
- Google 連携を使う場合は、Google Cloud の「認可済みのリダイレクト URI」に  
  `https://＜あなたのサービス名＞.onrender.com/settings/drive/callback` を追加する

---

## 3. データベース（PostgreSQL）

Render のファイルシステムはエフェメラルなため、**SQLite は再デプロイで消えます**。本番では PostgreSQL を使います。

### 選択肢

- **Render PostgreSQL**  
  - 同じ Render アカウントで **New** → **PostgreSQL** を作成  
  - 作成後、**Info** の **Internal Database URL** をコピーし、Web サービスの `DATABASE_URL` に設定  
  - 無料 DB は **30 日で削除**されるため、長期利用なら有料プラン（$7/月）か外部 DB を検討
- **外部 PostgreSQL**  
  - [Neon](https://neon.tech) や [Supabase](https://supabase.com) の無料枠の接続 URL を `DATABASE_URL` に設定

---

## 4. デプロイと確認

1. **Create Web Service** でデプロイ開始
2. ビルド・デプロイが終わったら、画面上部の **URL**（例: `https://account-book.onrender.com`）でアクセス
3. 初期設定画面や取引一覧が表示されれば成功

---

## 5. 注意点（無料枠）

- **15 分無操作でスリープ**し、次のアクセスで約 1 分ほど起動時間がかかることがあります
- **領収書画像**はサーバーに永続しないため、**Google Drive 連携**での保存を推奨します
- コードを更新したら GitHub にプッシュすると、Render が自動で再デプロイします

---

## 6. 正式運用時に Heroku へ移行する場合

- 同じ `wsgi.py`・`Procfile`・環境変数（`DATABASE_URL`, `SECRET_KEY` 等）で **Heroku** にデプロイ可能
- Heroku では **Eco Dyno** + **Postgres** で月約 $10 程度。手順は Heroku の Flask 公式ドキュメントを参照

詳細な比較は `docs/公開サーバー選び_RenderとHeroku.md` を参照してください。

---

## Start Command の場所（見つからないとき）

Render で **Start Command** を変えるには、次の順で開きます。

1. [Dashboard](https://dashboard.render.com) で、該当の **Web サービス**をクリック
2. 左側メニューで **「Settings」**（設定）をクリック
3. ページ内の **「Build & Deploy」** セクションまでスクロール
4. **Build Command** の下あたりに **「Start Command」** の入力欄がある  
   - ここが `gunicorn your_application.wsgi` のままなら、**`gunicorn wsgi:application`** に書き換える
5. 画面下の **「Save Changes」** を押してから、**Manual Deploy** で再デプロイ

**別の見方**: サービス詳細の左メニューに **Environment** しかない場合、**Settings** タブ（またはサービス名の横の歯車アイコン）を開くと、Build Command / Start Command がまとまっていることがあります。

---

## よくあるエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| `ModuleNotFoundError: 'your_application'` / `'your_application' is not a package` | Start Command がデフォルトのまま | **方法A**: 上記「Start Command の場所」のとおり **Settings** → **Build & Deploy** で **Start Command** を `gunicorn wsgi:application` に変更。**方法B**: リポジトリに `your_application/` パッケージ（`__init__.py` と `wsgi.py`）を入れておけば、Start Command を変更しなくてもデフォルトの `gunicorn your_application.wsgi` のまま動く（このリポジトリにはすでに含まれています）。 |
