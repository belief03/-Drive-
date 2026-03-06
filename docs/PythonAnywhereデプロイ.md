# PythonAnywhere へのデプロイ手順

このドキュメントでは、青色申告帳簿ツールを **PythonAnywhere の無料プラン** で公開する手順を説明します。

---

## 前提

- GitHub にリポジトリがプッシュ済みであること
- PythonAnywhere のアカウント（未登録なら [https://www.pythonanywhere.com](https://www.pythonanywhere.com) で無料登録）

---

## 1. アカウント作成とダッシュボード

1. [PythonAnywhere](https://www.pythonanywhere.com) にアクセスし、**Pricing** から **Create a Beginner account**（無料）で登録する。
2. ログイン後、**Dashboard** が表示される。

---

## 2. GitHub からコードを取得

1. ダッシュボード上部の **Consoles** タブを開く。
2. **$ Bash** をクリックして Bash コンソールを開く。
3. 次のコマンドを実行する（`<あなたのユーザー名>` と `<リポジトリ名>` は実際の GitHub の値に置き換える）。

```bash
cd ~
git clone https://github.com/<あなたのユーザー名>/<リポジトリ名>.git account-book
cd account-book
```

例: `git clone https://github.com/myuser/account-book.git account-book`

---

## 3. 仮想環境の作成とパッケージ導入

Bash コンソールで続けて実行する。

```bash
cd ~/account-book
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- Python 3.10 が無い場合は `python3 -m venv venv` など、利用可能なバージョンに合わせる。
- エラーが出た場合は表示内容を確認し、必要なパッケージが `requirements.txt` に含まれているか確認する。

---

## 4. Web アプリの作成

1. ダッシュボードで **Web** タブを開く。
2. **Add a new web app** をクリック。
3. **Next** を押し、**Flask** を選んで **Next**。
4. **Python 3.10**（または利用可能なバージョン）を選び **Next**。
5. **Project name** はそのまま（例: `account-book`）で **Next**。  
   → これでいったん Flask のサンプルが作成される。

---

## 5. Web アプリの設定

1. **Web** タブの **Code** セクションで次を設定する。

| 項目 | 入力例（パスは自分の環境に合わせる） |
|------|--------------------------------------|
| **Source code** | `/home/＜あなたのユーザー名＞/account-book` |
| **Working directory** | `/home/＜あなたのユーザー名＞/account-book` |

2. **Virtualenv** の欄で **Enter path to a virtualenv** を選び、次を入力する。

```
/home/＜あなたのユーザー名＞/account-book/venv
```

3. **WSGI configuration file** のリンクをクリックして WSGI ファイルを開く。  
   中身を **すべて削除** し、次の内容だけにする（`your-username` を自分のユーザー名に変更）。

```python
import sys
import os

path = '/home/your-username/account-book'
if path not in sys.path:
    sys.path.insert(0, path)

os.chdir(path)

from wsgi import application
```

4. 上書き保存する（**Ctrl+S** または **Save**）。

---

## 6. 環境変数（本番用）

1. **Web** タブの **Code** セクションの下にある **Environment variables** を開く（または **Configuration for ～** 内のリンク）。
2. 次の変数を追加する（値は各自で設定）。

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `SECRET_KEY` | 本番用の秘密鍵（ランダムな長い文字列） | 自分で生成した文字列 |
| （任意）`GOOGLE_DRIVE_CLIENT_ID` | Google 連携を使う場合 | クライアント ID |
| （任意）`GOOGLE_DRIVE_CLIENT_SECRET` | Google 連携を使う場合 | クライアントシークレット |
| （任意）`GOOGLE_DRIVE_REDIRECT_URI` | Google 連携を使う場合 | `https://＜あなたのユーザー名＞.pythonanywhere.com/settings/drive/callback` |

- **SECRET_KEY** は必ず本番用に設定する（例: ターミナルで `python -c "import secrets; print(secrets.token_hex(32))"` で生成）。
- Google 連携を使う場合は、Google Cloud の「認可済みのリダイレクト URI」に  
  `https://＜あなたのユーザー名＞.pythonanywhere.com/settings/drive/callback`  
  を追加する。

---

## 7. 静的ファイル・静的 URL マッピング（任意）

このアプリは静的ファイルをあまり使っていないため、必須ではありません。  
必要になったら **Web** タブの **Static files** で、`/static/` を `~/account-book/static` などにマッピングする。

---

## 8. リロードと動作確認

1. **Web** タブの **Reload** ボタン（緑色）をクリックする。
2. 画面上部に表示されている **URL**（例: `https://＜あなたのユーザー名＞.pythonanywhere.com`）をブラウザで開く。
3. 初期設定画面や取引一覧が表示されればデプロイ成功。

---

## 9. よくあるエラーと対処

| 現象 | 対処 |
|------|------|
| **500 Error** | **Web** タブの **Error log** を開き、メッセージを確認。パス・仮想環境・WSGI の `from wsgi import application` が正しいか確認。 |
| **ModuleNotFoundError** | 仮想環境が正しく指定されているか、Bash で `source venv/bin/activate` のうえ `pip install -r requirements.txt` を再度実行。 |
| **ImportError (app)** | WSGI の `path` が `/home/＜ユーザー名＞/account-book` になっているか、`from wsgi import application` になっているか確認。 |
| **instance がない** | 初回アクセスでアプリが `instance` フォルダを作成する。それでもエラーなら、Bash で `mkdir -p ~/account-book/instance` を実行してリロード。 |

---

## 10. コードを更新したとき

GitHub にプッシュしたあと、PythonAnywhere 側で次を実行する。

```bash
cd ~/account-book
git pull
```

その後、**Web** タブの **Reload** をクリックする。

---

## まとめ

- **Source code / Working directory**: `~/account-book`
- **Virtualenv**: `~/account-book/venv`
- **WSGI**: 中身を `from wsgi import application` を読み込む内容に変更
- **SECRET_KEY** を必ず本番用に設定
- Google 連携を使う場合は本番 URL をリダイレクト URI に追加

以上で、無料の範囲内で PythonAnywhere にデプロイできます。
