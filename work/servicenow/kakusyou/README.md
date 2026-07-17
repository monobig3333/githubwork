# 非機能要件 性能・可用性 確証テストコード

ServiceNow 統合管理コンソール導入における非機能要件テストのソースコード一式。
要件No 単位でディレクトリを分け、それぞれ Playwright (Python) または Apache JMeter のスクリプトを配置している。

**Google SSO 認証対応**:
- Playwright → 手動で1回ログインして `auth.json` に保存（8時間有効）
- JMeter → OAuth Client Credentials Grant でBearerトークン取得（SSO非依存）

## ディレクトリ構成

```
kakusyou/
├── _common/                       共通モジュール
│   ├── config.py                  環境設定
│   ├── servicenow_auth.py         OAuth認証（Python）
│   ├── snow_client.py             ServiceNow REST APIクライアント
│   ├── playwright_helpers.py      Playwright計測ヘルパー
│   └── save_auth_state.py         storage_state保存スクリプト
├── conftest.py                    pytest 共通フィクスチャ（auth.json自動読込）
├── pytest.ini                     pytest 設定
├── requirements.txt               Python 依存パッケージ
├── .env.example                   環境変数テンプレート
├── jmeter.properties.example      JMeter プロパティテンプレート
├── auth.json                      Playwright storage_state（gitignore推奨）
├── README.md                      このファイル
├── 1-1/ … 13-1/                  性能・可用性要件
└── M-1/ … M-9/                   MIDサーバ可用性・性能要件
```

## 前提

- macOS / Linux
- Python 3.10+
- Apache JMeter 5.6+（Java 11/17/21）
- ServiceNow OAuth Application Registry に Client Credentials 用エンドポイント登録済み

## セットアップ

```bash
# Python 仮想環境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 環境変数
cp .env.example .env
# .env を編集：SNOW_INSTANCE, SNOW_BASE_URL, MID_HOSTS など

# JMeter プロパティ
cp jmeter.properties.example jmeter.properties
# jmeter.properties を編集：snow.client_id, snow.client_secret
```

## SSO 環境での認証フロー

### Playwright 用：auth.json の取得（8時間ごとに再実行）

```bash
# Chromium が立ち上がるので、Google SSO で手動ログイン
# ServiceNow のホーム画面まで遷移したらターミナルで Enter
python3 _common/save_auth_state.py
```

`auth.json` がルート直下に作成され、conftest.py が自動でこれを読み込む。
セッションが切れた（8時間経過）ら同じコマンドで再生成する。

### JMeter 用：OAuth クレデンシャル

ServiceNow で OAuth Application Registry を開き、
**Application Registry → New → Create an OAuth API endpoint for external clients** を作成。

- Client ID / Client Secret を取得
- `jmeter.properties` の `snow.client_id` / `snow.client_secret` に貼り付け

各 JMX には setUp Thread Group が組み込まれており、テスト開始時に
`POST /oauth_token.do` でアクセストークンを取得し、以降のリクエストの
`Authorization: Bearer ...` ヘッダに自動セットされる。

## 実行方法

### Playwright (pytest)

```bash
pytest 1-1/                       # 単一要件
pytest -v                         # 全要件
pytest 1-1/ --headed              # ブラウザを表示
pytest -m "perf and not high_load"  # マーカーで絞り込み
```

### JMeter

```bash
# 非GUI実行
jmeter -n -t 1-2/1-2_concurrent_165.jmx \
  -p jmeter.properties \
  -l 1-2/result.jtl \
  -e -o 1-2/report/

# 軽量スモークテスト（1スレッドで疎通確認）
jmeter -n -t 1-2/1-2_concurrent_165.jmx \
  -p jmeter.properties \
  -Jthreads=1 -l /tmp/smoke.jtl
```

## 要件一覧

| 要件No | 区分 | テスト項目 | ツール |
|---|---|---|---|
| 1-1 | 性能/SD | 画面応答時間（通常操作） | Playwright |
| 1-2 | 性能/SD | 同時接続165クライアント | JMeter |
| 1-3 | 性能/SD | 同時接続330クライアント（参照専用） | JMeter |
| 1-4 | 性能/SD | チケット起票数（月間処理量） | Playwright |
| 2-1 | 性能/AV | アラームビューワー同時接続165 | JMeter |
| 2-2 | 性能/AV | アラーム処理性能（最大負荷） | JMeter |
| 2-3 | 性能/AV | アラーム描画応答時間（通常時） | Playwright |
| 2-4-5 | 性能/AV | アラーム描画応答時間（高負荷時） | JMeter+Playwright |
| 2-6 | 性能/AV | アラーム描画応答時間（高負荷30分） | JMeter+Playwright |
| 3-1 | 性能 | ワークフロー並列実行 | JMeter |
| 4-1 | 性能 | 構成情報100万件 | Python (REST) |
| 7-3 | 可用性 | 系切り替え後データ継続性 | Playwright |
| 13-1 | 拡張性 | ユーザ・データ量2倍 | JMeter+Playwright |
| M-1 | MID性能 | 転送スループット（通常時） | JMeter |
| M-2 | MID性能 | 転送スループット（最大負荷） | JMeter |
| M-3 | MID性能 | 高負荷継続性能飽和 | JMeter |
| M-4 | MID性能 | リソース使用率 | Shell (top/vmstat) |
| M-5 | MID可用 | 1AZ停止時イベント転送 | JMeter+Playwright |
| M-6 | MID可用 | 2AZ停止時イベント転送 | JMeter+Playwright |
| M-7 | MID可用 | データロスなし確認 | Python (ログ突合) |
| M-8 | MID可用 | 停止AZ自動復旧 | Playwright |
| M-9 | MID可用 | 全AZ停止挙動・復旧後再送 | Python (ログ突合) |

ドキュメントレビューのみで判定する 7-1, 7-2, 7-4, 7-5-6-7, 9-1, 9-2 はコード対象外。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| pytest が `auth.json が存在しない…` でスキップ | storage_state 未生成 | `python3 _common/save_auth_state.py` を実行 |
| Playwright で「ログインページにリダイレクト」 | auth.json のセッション期限切れ | 同上、auth.json を再生成 |
| JMeter で OAuth setUp が 401 | client_id/secret 不正 or OAuth未有効化 | ServiceNow Application Registry で確認 |
| JMeter で 「access_token を取得できない」 | setUp Thread Group のレスポンス確認 | View Results Tree で `/oauth_token.do` のレスポンス確認 |
