# CLAUDE.md

このファイルは Claude Code (claude.ai/code) が本リポジトリで作業する際の指針を提供する。

## リポジトリ概要

ServiceNow 統合管理コンソール導入の **性能・可用性・非正常系試験** 関連の試験コード・スクリプト・ドキュメント一式。

- 対象 ServiceNow バージョン: **Zurich**
- 対象インスタンス: `biglobenonprod` (主) / `biglobedev` (一部初期検証)
- MID Server: 3 AZ 構成 (stg-1 / stg-2 / stg-3)
- 試験項目数: 34 (出荷条件 33 + 参考値 1)
- 全試験結果: **出荷条件 33 件すべて OK**

## ディレクトリ構成

```
kakusyou/
├── CLAUDE.md                                 ← 本ファイル
├── README.md                                 セットアップ・実行方法
├── 性能・可用性・非正常系テスト計画書.xlsx       テスト計画書 (旧: 非機能要件テスト計画書)
├── 性能・可用性・非正常系試験_評価報告書.pptx     評価報告書 (slide deck)
├── 性能・可用性・非正常系試験_評価報告書.pdf      評価報告書 PDF 版
│
├── _common/                       Python 共通モジュール
│   ├── config.py                  環境設定 (.env 読込)
│   ├── servicenow_auth.py         OAuth Client Credentials 認証 (一部試験用)
│   ├── snow_client.py             ServiceNow REST API クライアント (一部試験用)
│   ├── playwright_helpers.py      Playwright 計測ヘルパー (iframe / measure / summarize)
│   ├── save_auth_state.py         Google SSO + MFA storage_state 保存 (永続プロファイル方式)
│   ├── check_form_login.py        SNOW_USER/SNOW_PASSWORD でフォームログイン疎通確認
│   └── check_zabbix_connector.py  em_connector_instance の状態確認・継続モニタ
│
├── N-common/                      非正常系試験 共通モジュール
│   ├── verify_continuity.py       em_event 到達継続性 検証 (手元実行)
│   └── verify_mid_status.py       ecc_agent.status 変化検出 (手元実行)
│
├── conftest.py                    pytest 共通フィクスチャ (auth.json 自動読込)
├── pytest.ini                     pytest 設定
├── requirements.txt               Python 依存パッケージ
├── jmeter.properties              JMeter プロパティ (秘匿情報)
├── jmeter.properties.example      JMeter テンプレート
├── auth.json                      Playwright storage_state (gitignore)
├── .env                           環境変数 (秘匿情報)
├── .env.example                   .env テンプレート
├── .playwright-profile/           Chromium 永続プロファイル (gitignore)
│
├── 1-1/ … 4-1/                    性能 要件 (サービスデスク / アラームビューワー / ワークフロー / 構成情報)
├── 7-1/ … 9-2/                    可用性・災害対策 要件
├── M-1/ … M-9/                    MID サーバ 性能・可用性 要件
├── M10/                           外部試験成果物 (Trap 送信)
├── M11/                           外部試験成果物 (メール通知 ※参考値)
└── N-1/ … N-5/                    MID サーバ 非正常系 (新設)
```

## 試験項目マトリクス

### 性能 (15 件)

| カテゴリ | 要件 | 主なツール |
|---|---|---|
| サービスデスク | 1-1, 1-2, 1-3, 1-4 | Playwright + JMeter |
| アラームビューワー | 2-1, 2-2, 2-3, 2-4/5, 2-6 | Playwright + Zabbix 外部投入 |
| ワークフロー | 3-1 | JMeter (incident 並列起票) |
| 構成情報 | 4-1 | 専用スクリプト |

### 可用性・災害対策 (7 件)

ServiceNow 社方針により実機試験不可。**Trust Center / SLA 資料によるドキュメントレビュー方式** で代替: 7-1, 7-2, 7-3, 7-4, 7-5/6/7, 9-1, 9-2 すべて OK。

### MID サーバ 性能 (5 件 + 参考 1 件)

| 要件 | 内容 | 補足 |
|---|---|---|
| M-1〜M-3 | イベント転送スループット系 | Zabbix 外部負荷投入 |
| M-4 | リソース使用率 | `monitor_local.sh` ローカル実行 |
| M-10 | Trap 送信テスト | 外部試験 |
| **M-11** | **メール通知送信機能** | **参考値・出荷条件外** (メール経由の全機器障害通知は設計想定外) |

### MID サーバ 可用性 (5 件)

M-5〜M-9: AZ 停止系試験。

### MID サーバ 非正常系 (5 件・新設)

N-1〜N-5: Disk I/O / CPU / メモリ / Disk Full / TCP 枯渇。各 MID 上でローカル負荷スクリプト + 手元から継続性検証。

## 認証パターン

### REST API 呼び出し
- **方式**: `auth.json` の cookie + `X-UserToken` (`window.g_ck`) ヘッダ
- OAuth Client Credentials / AWS Secrets Manager は **不要**
- 関連: `N-common/verify_continuity.py` / `2-3/test_2_3_alarm_render.py` 等

### Playwright 画面操作
- 既存 `auth.json` を `storage_state` として読み込む (`conftest.py`)
- Google SSO + MFA で取得: `python3 _common/save_auth_state.py`
- `.playwright-profile/` を永続化、2 回目以降 MFA スキップ
- セッション有効期間: 約 8 時間

### JMeter
- OAuth Client Credentials Grant (`/oauth_token.do`)
- `jmeter.properties` の `snow.client_id` / `snow.client_secret`
- setUp Thread Group で取得した token を `${snow.token}` 変数に展開

## 共通的な実行パターン

### pytest (Playwright) 試験

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
pytest 2-3/ -v -s          # -s は input() プロンプト表示のため必須
```

### JMeter 試験

```bash
jmeter -n -t 1-2/1-2_concurrent_165.jmx -p jmeter.properties \
  -l 1-2/result.jtl -e -o 1-2/report/
# パラメタ上書き
jmeter -n -t 1-2/...jmx -Jthreads=165 -Jramp_up=30 ...
```

### 非正常系 (3 端末構成)

```bash
# 端末 A (手元)
python3 N-common/verify_continuity.py --label N-1 --duration 600 --max-gap 60 --output N-1/result.json

# 端末 B (MID Server stg-1)
bash /tmp/stress_disk_io.sh 600

# 端末 C (Zabbix 側) - 既存運用イベントで十分なケース多
```

`Enter で計測開始 >` プロンプトで両端末同期。

## 試験ごとの結果ファイル規約

| ファイル | 役割 |
|---|---|
| `<要件>/result*.json` | 生データ・統計 (テストごとに自動生成) |
| `<要件>/RESULT.md` | 判定サマリ・観察事項・実施情報 (人手で書く) |
| `<要件>/result_run<N>.json` | 過去 Run の保管 (やり直し時に rename) |

## Excel テスト計画書の規約

`性能・可用性・非正常系テスト計画書.xlsx` を Python で更新する際の規約:

- 日付列 (実施日): **文字列で `YYYY/M/D` 形式** (例: `2026/6/5`、ゼロ埋めなし、スラッシュ区切り)
- 結果列: `OK` / `NG` / `△` / `参考` / `未実施`
- M-x / N-x を追加するときは `insert_rows()` の後、凡例行のマージ (`A<R>:L<R>`) を unmerge → 再 merge する必要あり
- スタイルは M-9 行を template にコピー (`copy_style()` ヘルパー参照)

## 重要な学び (Learnings)

これらは過去にハマったポイント。同じ問題に当たったら参照する:

### 1. REST API の認証
- ServiceNow Zurich の REST API は **cookie だけでは 401** を返す
- `X-UserToken` ヘッダに `window.g_ck` の値を載せる必要あり
- `Referer` ヘッダも `em_event_list.do` 等の正規 URL に設定

### 2. 高負荷時の em_event 検知
- `ORDERBYsys_created_on` (昇順) でポーリングすると、新着順表示のビューワー 1 ページ目から押し出され DOM で見つからない
- **降順 `ORDERBYDESC` + 計測済 sys_id 除外** で安定

### 3. N-3 メモリ試験で MID Java を温存
- 単純に MemTotal × 80% を確保すると MID Java の Max ヒープ (4096MB) を奪い GC 飢餓で停止
- 既定計算式は **`MemTotal − MID_MAX_MB(4096) − OS_BUFFER_MB(512)`**

### 4. N-5 TCP 枯渇は sysctl 方式
- `ulimit -n` は systemd 起動の MID daemon に効かない
- OS グローバルの `ip_local_port_range` を sysctl で 32768-32800 (33 ポート) に縮小する方式に切替
- 復旧用 `/tmp/n5_orig_range` + 番犬プロセスで kill -9 でも自動復帰

### 5. M-11 メール通知は参考値
- メール経由の全機器障害通知は設計想定外
- 5,000 件処理に約 53 分かかるが **出荷条件には含めず参考値** として記録

### 6. Excel のシート構造
- 「非機能要件テスト計画」シートは **R3 がヘッダ** (R1 タイトル、R2 メタ)
- 「MIDサーバ テスト計画」シートは **R4 がヘッダ** (R1 タイトル、R2 メタ、R3 構成説明)
- `find_cols()` 系ユーティリティで `要件No` 列を検出してから操作する

### 7. Zabbix コネクタ バースト時取りこぼし (制限事項)
- ServiceNow サポート確認済の既知事象
- 発生条件: Zabbix の性能限界レベルの負荷 (ローカルからのバースト性能)
- 発生率: 0.02%
- 通常運用 (50 障害/秒以下) では再現せず
- 取りこぼしは Zabbix 側に残るため再送・運用回避可能
- **次回製品修正までの暫定制限事項**

## 環境変数 (.env)

```
SNOW_INSTANCE=biglobenonprod
SNOW_BASE_URL=https://biglobenonprod.service-now.com
SNOW_USER=mono                   # ローカルユーザ (フォームログイン用、MFA 有効)
SNOW_PASSWORD=...
ZABBIX_URL=https://10.249.73.66/zabbix/api_jsonrpc.php
ZABBIX_USER=mono
ZABBIX_PASSWORD=...
ZABBIX_TOKEN=...
ZABBIX_SCRIPT_ID=4               # script.execute 用 ID
ZABBIX_VERIFY_TLS=false
MID_HOSTS=mid-a.example.com,mid-b.example.com,mid-c.example.com
```

## 評価報告書の更新フロー

評価報告書 pptx は Node.js + pptxgenjs で生成:

```bash
# ローカル
node build_report.js 性能・可用性・非正常系試験_評価報告書.pptx

# PDF 化
soffice --headless --convert-to pdf 性能・可用性・非正常系試験_評価報告書.pptx
```

`build_report.js` 本体は別途管理。配色テーマは Midnight Executive (`#1E2761` navy + `#CADCFC` ice + `#FFC857` accent)。

## 注意・避けるべきこと

- 旧名 `非機能要件テスト計画書.xlsx` / `非機能要件_評価報告書.*` は削除済み。再生成時は新名 `性能・可用性・非正常系...` を使う
- `auth.json` / `jmeter.properties` / `.env` は gitignore 対象。コミットしない
- `.playwright-profile/` も gitignore。永続プロファイルなので機密 cookie を含む
- N-* の負荷スクリプトは MID 本番には絶対実行しない (stg-1 に限定)
- N-4 は既定で 100% Disk Full にする。`/tmp` と MID ログ FS が同じ場合は `TARGET=/var/tmp/n4.bin` で切替
- N-5 は sudo 必須、別経路 (コンソール or 別 SSH) を事前確保

## 作業終了時のルーティン

リポジトリは git 管理 (githubwork)。以下の順:

1. テスト結果が含まれる場合: `result*.json` は gitignore 対象なのでコミットしない
2. RESULT.md / README.md / Excel / pptx は git 管理 (履歴を残す)
3. コミットメッセージは `[要件No] 動作概要` 形式を推奨
4. `git push origin <branch>` でアップ

---

## クイックリファレンス

| やりたいこと | コマンド |
|---|---|
| auth.json 取り直し | `python3 _common/save_auth_state.py` |
| auth.json 生存確認 | `python3 2-3/api_probe.py` |
| 非正常系試験 N-1 | `python3 N-common/verify_continuity.py --label N-1 ...` + MID で `bash N-1/stress_disk_io.sh 600` |
| Zabbix コネクタ確認 | `python3 N-common/check_zabbix_connector.py --name zabbix` |
| Excel に試験結果書き込み | M-9 行をテンプレに copy_style + 実施日は `YYYY/M/D` 文字列 |
| 評価報告書再生成 | `node build_report.js ...` + `soffice --headless --convert-to pdf` |
