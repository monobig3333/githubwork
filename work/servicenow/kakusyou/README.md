# 性能・可用性・非正常系 確証テストコード

ServiceNow 統合管理コンソール導入における性能・可用性・非正常系テストのソースコード一式。
要件No 単位でディレクトリを分け、それぞれ Playwright (Python) または Apache JMeter のスクリプトを配置している。

- **対象インスタンス: `biglobedev`**（2026/8/14 以降の再測定）
- 再測定の計画・進捗・作業ログ: **`再測定_実行計画.md`**
- 開発時の注意点・過去の落とし穴: **`CLAUDE.md`**

**Google SSO 認証対応**:
- Playwright → 手動で1回ログインして `auth.json` に保存（**実測では約1時間で UI が不安定化するので長時間実行前に取り直す**）
- JMeter → OAuth Client Credentials Grant でBearerトークン取得（SSO非依存）

> ⚠️ `SNOW_USER` (ローカルユーザ) も dev では MFA が有効で、テスト内での自動再ログインには使えない。

## ディレクトリ構成

```
kakusyou/
├── _common/                       共通モジュール
│   ├── config.py                  環境設定
│   ├── servicenow_auth.py         OAuth認証（Python）
│   ├── snow_client.py             ServiceNow REST APIクライアント
│   ├── playwright_helpers.py      Playwright計測ヘルパー
│   ├── save_auth_state.py         storage_state保存スクリプト
│   ├── preflight_check.py         実測前の一括チェック
│   └── fetch_oauth_from_secrets.py Secrets Manager から OAuth を取得
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
```

### OAuth クレデンシャルの取得（AWS Secrets Manager）

`jmeter.properties` の client_id / secret は Secrets Manager から自動反映できる。

```bash
source setup.sh big4180 prd        # AWS 一時クレデンシャル（同じシェルで続ける）
python3 _common/fetch_oauth_from_secrets.py --show-keys   # キー名確認
python3 _common/fetch_oauth_from_secrets.py               # 疎通確認（dry-run）
python3 _common/fetch_oauth_from_secrets.py --write       # 反映（バックアップ自動作成）
```

Secret は `.env` の `SNOW_INSTANCE` から `servicenow/api-test/<instance>/admin-ai-api` を参照する。

### 実測前チェック

```bash
python3 _common/preflight_check.py
```

env / tools / auth / oauth / snow / mid / zabbix を一括確認する（負荷はかけない）。
FAIL が残っている状態で実測に進まないこと。

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

**`-p` ではなく `-q` を使う。** `-p` は既定の jmeter.properties を置き換えてしまい、
進捗サマリなどの既定設定が失われる。また `jmeter.properties` のグローバル値が
全 JMX の `__P()` 既定を上書きするため、**条件は必ず `-J` で明示指定する。**

```bash
# 非GUI実行
jmeter -n -t 1-2/1-2_concurrent_165.jmx -q jmeter.properties \
  -Jthreads=165 -Jramp_up=60 -Jloop.count=10 \
  -l 1-2/runs/run_$(date +%Y%m%d_%H%M%S).jtl

# 軽量スモークテスト
jmeter -n -t 1-2/1-2_concurrent_165.jmx -q jmeter.properties \
  -Jthreads=2 -Jramp_up=1 -Jloop.count=1 -l /tmp/smoke.jtl
```

本番計測時の条件は `再測定_実行計画.md` の 4 章にまとめてある。

### 1-4（1,000 件起票）

```bash
PERF_SUBMIT_MODE=submit pytest 1-4/ -v -s     # 本番 1,000 件（約 42 分）
```

`PERF_SUBMIT_MODE=submit` は**必須**。既定の「保存して留まる」では 4〜5 件で UI が停止する。

| 環境変数 | 用途 |
|---|---|
| `PERF_TICKET_COUNT` | 件数を絞る（指定するとスモーク扱いで別ファイルに出力） |
| `PERF_CONTEXT_EVERY` | N 件ごとにブラウザコンテキストを作り直す（既定 50） |
| `PERF_MAX_CONSEC_FAIL` | 連続失敗で打ち切る（既定 10） |
| `PERF_SLEEP_MS` | 起票間の待機 |

### 2-2（Zabbix からのイベント投入）

投入は **Zabbix サーバ上**で `zabbixtool/send_bulk.py` を実行する。
`on.py` は 1 件ごとにプロセスを起動するため 12.5 件/秒しか出ず、要件を満たせない。

```bash
# --- Zabbix サーバ側（必ず nohup + -u で。前面実行はセッション断で止まる）---
nohup python3 -u send_bulk.py --count 30000 --rate 50 --value 0 > /tmp/rec.log 2>&1 &   # ① 復旧
nohup python3 -u send_bulk.py --count 30000 --rate 50 > /tmp/run.log 2>&1 &             # ③ 投入
tail -f /tmp/run.log        # 表示だけ。Ctrl-C で抜けても投入は止まらない

# --- Mac 側 ---
python3 2-2/count_zabbix_events.py --from "HH:MM" --to "HH:MM" --show-problems  # ② PROBLEM=0 確認
python3 2-2/watch_em_event.py --once                             # 復旧分が流れ切るまで待つ
python3 2-2/watch_em_event.py --baseline <N> --interval 30       # 到達モニタ
python3 2-2/analyze_arrival.py --since "HH:MM"                   # 到達分析
```

**手順の順序が重要。**

1. 復旧（10 分）— これを省くとトリガーが PROBLEM のままでイベントが生成されない
2. PROBLEM が 0 件になったことを確認
3. **復旧イベント 30,000 件が流れ切るまで待つ（30〜40 分）** — 省くと今回分と混ざる
4. ベースラインを取って投入

詳細は `2-2/実行ガイド.md`。

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
| **Playwright で `page.goto` が 30 秒タイムアウトし続ける** | auth.json のセッションが弱っている（実測で約1時間） | `save_auth_state.py` で取り直す。curl は通るのに UI だけ落ちるのが特徴 |
| **1-4 が 4〜5 件で全滅する** | `sysverb_insert_and_stay` を使っている | `PERF_SUBMIT_MODE=submit` を指定 |
| **JMeter が全件エラーだが responseCode は 201** | Response Assertion が 200 のみ許容 | JMX のアサーションに 201 を追加 |
| **JMeter だけ 400 Bad Request（curl は成功）** | HeaderManager の `Authorization` が重複 | JMX のヘッダ定義を確認して重複を削除 |
| JMeter で OAuth setUp が 401 | client_id/secret がそのインスタンス向けでない | OAuth アプリはインスタンス単位。`fetch_oauth_from_secrets.py --write` で反映 |
| JMeter で 「access_token を取得できない」 | setUp Thread Group のレスポンス確認 | View Results Tree で `/oauth_token.do` のレスポンス確認 |
| **Zabbix に投入したのにイベントが増えない** | トリガーが PROBLEM のまま | `send_bulk.py --value 0` で先に復旧させる |
| **Zabbix の `host.get` が 0 件を返す** | `searchWildcardsEnabled` により完全一致になっている | `startSearch: True` を使う |
| **投入が途中で止まる（Zabbix 生成が中断）** | セッション断でプロセスが終了 | `nohup python3 -u ... &` で実行。`ps aux \| grep "[s]end_bulk"` で稼働確認 |
| **nohup のログに何も出ない** | Python の stdout がバッファされている | `python3 -u` を付ける |
| **MID が Down のまま起動しない** | conf 配下に他ユーザ所有のファイルがある | `find .../conf -name "*.bak_*" -exec mv {} /root/ \;` + `chown -R mid-server:mid-server .../conf` |
| **MID のメモリを増やしても改善しない** | `wrapper.java.maxmemory` が小さいまま | `conf/wrapper-override.conf` に `wrapper.java.maxmemory=4096`。**バックアップは conf の外へ** |
| **`gs.dateGenerate()` の絞り込みが 9 時間ずれる** | セッションTZで解釈されるのに UTC を渡している | JST の値をそのまま渡す |
| `jmeter ... -e -o report/` が `folder is not empty` | 前回のレポートが残っている | `-o report_$(date +%Y%m%d)/` のように別フォルダへ出す |
