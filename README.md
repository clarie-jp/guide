# クラリエ 生前整理・遺品整理ガイド（SEO記事の自動生成サイト）

- `keywords.csv` … 記事のキーワード表。status が todo の行から、priority の小さい順に生成される
- `scripts/generate.py` … Claude API で記事を生成し `content/posts/` に保存（品質チェック付き）
- `scripts/build.py` … Markdown から `dist/` に静的サイトを生成（記事・カテゴリ・タグ・著者・sitemap・RSS・構造化データ）
- `.github/workflows/daily.yml` … 毎日 06:10 JST に生成→コミット→ビルド→GitHub Pages に公開
- `site.yaml` … サイト名・URL・連絡先・著者・1回の生成本数・公開前レビューの有無

## 初回セットアップ
1. リポジトリの Settings → Secrets and variables → Actions → New repository secret に `ANTHROPIC_API_KEY` を登録
2. Settings → Pages → Source を「GitHub Actions」にする
3. Actions タブ → 「記事の自動生成と公開」→ Run workflow（count に 3 などを入れると、その本数を生成）

## 運用
- キーワードを足す：`keywords.csv` に行を追加（priority, category, keyword, intent, angle, status=todo）
- 公開前に目を通したい：`site.yaml` の `review_before_publish: true` にすると `content/drafts/` に出力される。確認して `content/posts/` に移すと公開される
- 記事を直す：`content/posts/*.md` を編集して push すると自動で再ビルド
- URLを独自ドメインにする：`site.yaml` の `base_url` を変え、`static/CNAME` にドメインを書く

## ローカルで試す
```
pip install pyyaml markdown
python3 scripts/generate.py --dry-run      # 次に書くキーワードを表示
ANTHROPIC_API_KEY=... python3 scripts/generate.py --count 1
python3 scripts/build.py && python3 -m http.server -d dist 8000
```


## 2026-11-09 更新：公開先を guide.clarie.jp（お名前.com レンタルサーバー）に変更

- 公開URL: https://guide.clarie.jp （site.yaml の base_url）。第2段階で https://clarie.jp/guide に移す場合は base_url だけ変更
- 配信: GitHub Actions でビルド → rsync over SSH でサーバーへ転送（GitHub Pages は使わない）
- 必要な Secrets: ANTHROPIC_API_KEY / SSH_HOST / SSH_USER / SSH_KEY / DEPLOY_PATH（SSH_PORT は省略可）
- トップページは LP（文言は site.yaml の lp:）
- 記事は4領域（basic/area/case/item）を site.yaml の mix の比率で生成。事例は cases.csv の実データのみから生成
- 1日の生成本数: posts_per_run（既定3）

### 接続情報（2026-11-09 設定済み。秘密鍵・APIキーは GitHub Secrets のみに保管）
- サーバー: www1222.onamae.ne.jp（お名前.com レンタルサーバー ベーシック、契約番号 2446171、CPユーザー rs2446171）
- SSH: ポート 8022、ユーザー r3199320、鍵名 github-actions-clarie-guide（ed25519、公開鍵はCP → サーバー → SSH に登録済み）
- 公開ディレクトリ（DEPLOY_PATH）: /home/r3199320/public_html/guide.clarie.jp/
- DNS: clarie.jp は CP の DNS で管理（本体 A → 34.111.141.225 = STUDIO、www → 157.120.209.206）。guide はサブドメイン追加時に自動設定
- SSL: 無料SSL（アルファSSL）を guide.clarie.jp に申込み済み
- 国外アクセス制限（SSH）: オフのまま（GitHub Actions は海外IPのため）

### 初回セットアップ手順
1. お名前.com コントロールパネル: ドメイン → clarie.jp → サブドメイン「guide」を追加（公開ディレクトリのパスを控える）
2. サーバー → SSH → key の新規自動作成（秘密鍵をダウンロード）
3. セキュリティ → SSL証明書 → guide.clarie.jp に無料SSLを設定
4. GitHub に clarie-jp/guide を作成し、このフォルダの中身を push
5. Settings → Secrets and variables → Actions に上記 Secrets を登録（DEPLOY_PATH は手順1のパス、末尾スラッシュあり）
6. Actions → 「記事の自動生成と公開」→ Run workflow（count=3）で初回実行
7. Google Search Console に guide.clarie.jp を登録し、sitemap.xml を送信

## 整合性ルール（2026-11-09〜）
- 料金・電話番号・受付時間・対応エリア・追加請求の扱いは **site.yaml だけ** が正。LP・記事・Googleマップ投稿はすべてここに合わせる
- `scripts/consistency.py` が、記事生成時（不採用にする）とビルド時（公開を止める）の両方でチェックする
- 料金を変えるときは site.yaml の `lp.pricing.rows` を直し、既存記事もビルドが通るように直してから公開する
