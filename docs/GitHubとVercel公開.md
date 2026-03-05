# GitHub 連携と Vercel での公開

## 1. GitHub に連携する（公開前の準備）

### 1.1 このリポジトリでやること

- **`.gitignore`** により、次は **GitHub に含まれません**（すでに設定済み）:
  - `instance/` フォルダ（DB・領収書画像・**Google のクライアントID・シークレット**）
  - `venv/` などの仮想環境
  - `.env`（環境変数をファイルで管理する場合）

**重要**: クライアントシークレットや DB は絶対にリポジトリにコミットしないでください。

### 1.2 GitHub にプッシュする手順

1. **Git が未初期化の場合**
   ```bash
   cd "G:\マイドライブ\coursor\account book"
   git init
   ```

2. **リモートを追加**（GitHub で新規リポジトリを作成したあと）
   ```bash
   git remote add origin https://github.com/＜あなたのユーザー名＞/＜リポジトリ名＞.git
   ```

3. **コミットしてプッシュ**
   ```bash
   git add .
   git status   # instance/ や .env が含まれていないか確認
   git commit -m "Initial commit: 青色申告帳簿ツール"
   git branch -M main
   git push -u origin main
   ```

4. **GitHub でリポジトリを「Private」にしておく**と、ソースと設定が非公開になります。

---

## 2. Vercel で公開するときの注意

このアプリは **Flask + SQLite** の従来型 Web アプリです。Vercel は **サーバーレス** のため、そのままでは動かず、次の点を変更する必要があります。

### 2.1 主な制約

| 項目 | 内容 |
|------|------|
| **DB** | Vercel のファイルシステムは読み取り専用のため、**SQLite は使えません**。Vercel Postgres や外部の PostgreSQL などに変更する必要があります。 |
| **ファイル保存** | 領収書画像や `instance/` への保存は永続しません。S3 や Vercel Blob など外部ストレージが必要です。 |
| **セッション** | サーバーレスではメモリが共有されないため、Cookie ベースのセッションは **Vercel KV** や **Redis** などで保存する必要があります。 |
| **Google 連携** | 本番の URL（例: `https://xxx.vercel.app`）を Google Cloud の「認可済みのリダイレクト URI」に追加する必要があります。 |

### 2.2 進め方の例

1. **まず GitHub にプッシュ**  
   上記の手順で、コードだけ先に GitHub に上げる。

2. **Vercel にデプロイする場合**
   - Vercel は「GitHub リポジトリを連携してデプロイ」が基本です。
   - ただし **Flask + SQLite のままでは動作しません**。
   - 公開するには次のいずれかが必要です:
     - **A)** DB を Vercel Postgres や Supabase などに変更し、ファイル保存を Blob 等に変更する（コード修正が必要）
     - **B)** Flask 向けの **PaaS**（Render, Railway, Heroku など）でデプロイする（SQLite やファイル保存が使いやすい）
     - **C)** 自前サーバーや VPS で `python app.py` または Gunicorn で動かす

3. **Vercel で「静的サイト＋API」にする場合**  
   フロントだけ Vercel、API は別サーバーにする構成も可能ですが、設計の見直しが必要です。

---

## 3. まとめ

- **GitHub 連携**: `.gitignore` を確認したうえで、`git init` → `remote add` → `add` → `commit` → `push` でリポジトリに反映できます。
- **Vercel 公開**: このアプリは現状のままでは Vercel で動きません。公開する場合は、DB とファイル保存をクラウド向けに変更するか、Render / Railway など Flask 向けのサービスを検討してください。

DB を Postgres に変更するなど、Vercel 対応用の具体的な修正方針が必要であれば、その旨を伝えてもらえれば手順をまとめます。
