# snowmessagechk

ServiceNow `em_event` テーブルに仕様書通りのデータが登録されているかをチェックするプログラム群。

## 本番環境 (biglobeprod) の取り扱い

**本番環境に対してアクション（スクリプト実行・データ取得・変更等）を行う前に、必ずユーザーに確認を取ること。**

- 本番インスタンス: `https://biglobeprod.service-now.com`（`.env` のデフォルト）
- 本番シークレット: `servicenow/api/credentials/biglobeprod/admin-ai-api`
- 非本番インスタンス: `https://biglobenonprod.service-now.com`

確認文例:「本番環境 (biglobeprod) に対して実行しますがよろしいですか？」

## 概要

- ServiceNow の REST Table API に OAuth2 (client_credentials) で接続
- 認証情報は AWS Secrets Manager から取得（または `.env` に直書きも可）
- AWS 認証は `setup.sh` で一時クレデンシャルをシェル環境にセットしてから使う
- 仕様書: `specification/event.xlsx`（シート「確定版Log → Event」が主仕様）

## ファイル構成

| ファイル | 役割 |
|---|---|
| `snow_client.py` | ServiceNow API 共通クライアント（トークン取得・テーブル GET/POST） |
| `get_events.py` | em_event テーブルからレコードを取得して JSON 出力 |
| `setup.sh` | AWS 一時クレデンシャルをシェルに export するセットアップスクリプト |
| `.env` | 環境変数定義（`SNOW_BASE_URL`, `SNOW_SECRET_NAME` 等） |
| `specification/event.xlsx` | ログ → イベントマッピング仕様書 |
| `tmpdir/` | 仕様書・一時ファイル置き場（git 管理外） |
| `datakaiseki/` | 調査用データ置き場（git 管理外）。CI未バインド分析用 CSV 等 |
| `datakaiseki/analyze_syslog_alerts.py` | syslog アラートを description パターン別に分類・CI バインド状況・CMDB照合・対処パターン（A/B/C/D）を Excel 出力 |

### alertchk/ ディレクトリ（アラートチェックツール）

| ファイル | 役割 |
|---|---|
| `alertchk/check_alerts.py` | em_alert 全件をイベントルール仕様書と照合してサマリー／詳細／JSON 出力 |
| `alertchk/check_ci_unbound.py` | CI未バインドアラートを取得しソース別分類・CMDB照合・Excel出力（ファイル名に日付自動付与）。Zabbix/CloudWatchLogs/HIOS(SV)/HIOS(AWS) の各シート末尾に疑義CI CMDB照合表を追加。`--query` で日付範囲絞り込み可 |
| `alertchk/alert_validators.py` | 変換後ソース識別とフィールドバリデーションロジック |
| `alertchk/get_alert.py` | sys_id を指定して em_alert の1件を表示 |

### cichk/ ディレクトリ（CI バインディング仕様解析ツール）

> **注意**: このインスタンスに `em_binding_rule` / `em_event_rule` は存在しない。
> **大半の CIバインドルールは `sa_event_rule` に格納されている（2026-06-15 判明）。**
> 実際のルール管理は以下のカスタムテーブル（`u_` プレフィックス）と標準テーブルで行われている。

| テーブル | 内容 | 件数 | 備考 |
|---|---|---:|---|
| `sa_event_rule` | CIバインドルール（イベントルール） | — | **主要**。大半のCIバインドルールはここ |
| `u_transformation_rule` | カスタムアラート変換ルール | 342件 | **主要**。カテゴリ5種 |
| `u_transformation_rule_detail` | 変換ルール詳細（フィールド変換値） | 675件 | 親ルールへの参照あり |
| `u_ignore_rule` | アラート無視ルール（メンテ抑止等） | 180件 | 期間指定 |
| `u_alert_type` | アラートタイプ定義 | 64件 | |
| `em_rule_xml` (matchRule) | CIバインディングルール（XML） | 8件 | 旧世代ソース向け |
| `em_rule_xml` (fieldMappingRule) | フィールドマッピングルール（XML） | 9件 | 旧世代ソース向け |
| `em_mapping_rule` | フィールドマッピングルール | 62件 | |
| `em_binding_device_map` | CI タイプ間マッピング定義 | 12件 | |

`u_transformation_rule` のカテゴリ:

| カテゴリ | 総数 | 有効 |
|---|---:|---:|
| 通常抑止フィルタ | 98 | 78 |
| アラートタイプ変換 | 69 | 60 |
| メッセージ変換 | 65 | 63 |
| ログ変換 | 60 | 59 |
| 監視種別変換 | 50 | 50 |

| ファイル | 役割 |
|---|---|
| `cichk/get_ci_bindings.py` | 上記全テーブルから仕様書（JSON/Excel）を生成 |
| `cichk/check_ci_bindings.py` | sa_event_rule / matchRule / em_mapping_rule / u_transformation_rule の完全性・整合性チェック |
| `cichk/ci_validators.py` | CI バインディング・変換ルール検証ロジック |
| `cichk/get_ci_binding.py` | sys_id を指定して sa_event_rule / em_rule_xml / em_mapping_rule の1件を表示 |

### eventchk/ ディレクトリ（仕様チェックツール）

| ファイル | 役割 |
|---|---|
| `eventchk/check_events.py` | em_event 全件を仕様書と照合してサマリー／詳細／JSON 出力 |
| `eventchk/validators.py` | データソース識別とフィールドバリデーションロジック |
| `eventchk/get_event.py` | sys_id を指定して em_event の1件を表示（ServiceNow REST API 経由） |
| `eventchk/get_event_athena.py` | sys_id を指定して Athena (`snow_prd.v_em_event`) から1件取得して JSON 表示 |

### mkevnet2dev/ ディレクトリ（開発環境イベント登録ツール）

Athena (`snow_prd.v_em_event`) 上の既存イベントを1件複製し、`time_of_event` を現在時刻に更新して開発インスタンス (`biglobedev`) の `em_event` に新規登録する。動作確認・再現テスト用。

- 登録先インスタンス: `https://biglobedev.service-now.com`
- API キー: AWS Secrets Manager `servicenow/api-test/biglobedev/admin-ai-api`（`bgl-big4180-prd` アカウント）。キー名は `ClientID`/`ClientSecret`（`biglobeprod` 用シークレットの `OAuthToken`/`OAuthSecret` とは異なる。`snow_client._get_credentials()` が両方に対応）
- `sys_id` / `sys_created_on` 等の `sys_*` 系システム管理列は新規登録ペイロードから除外

| ファイル | 役割 |
|---|---|
| `mkevnet2dev/create_event.py` | Athena から sys_id 指定で1件取得 → `time_of_event` を現在時刻化 → biglobedev の em_event へ新規登録 |

```bash
# ペイロード確認のみ（登録しない）
source ./setup.sh && python3 mkevnet2dev/create_event.py <event_sysid> --dry-run

# biglobedev へ新規登録
source ./setup.sh && python3 mkevnet2dev/create_event.py <event_sysid>
```

### zabbixcibind/ ディレクトリ（Zabbix CI バインド調査・テストツール）

biglobedev 環境で Zabbix イベントの CI バインド動作を調査・検証するツール群。

- 接続先: `https://biglobedev.service-now.com`
- シークレット: `servicenow/api-test/biglobedev/admin-ai-api`
- 調査対象イベントルール: `Zabbix_アラート作成ルール monotest 版 Device Mapping version`（sys_id=`4575a55e838283906c7d96b6feaad32c`, order=300）

| ファイル | 役割 |
|---|---|
| `zabbixcibind/diagnose_ci_bind.py` | イベントルール/CMDB/em_event/em_alert/em_binding_device_map を一括調査 |
| `zabbixcibind/send_test_event.py` | テストイベント投入 → 処理待機 → CI バインド結果を自動確認 |
| `zabbixcibind/update_event_rule.py` | em_match_rule の identification_rules を REST API で更新するユーティリティ |

## セットアップ

```bash
# AWS 一時クレデンシャルをシェルにセット（source で実行すること）
source ./setup.sh
```

> `setup.sh` は `source` 専用。直接実行するとエラーになる。

## 実行例（datakaiseki）

```bash
# syslog アラートを4月以降で取得・descriptionパターン別分類・CI未バインド対処分析
source ./setup.sh && python3 datakaiseki/analyze_syslog_alerts.py

# ファイル名は datakaiseki/syslog_alerts_YYYYMMDD.xlsx で自動生成
```

対処パターン:
- **A**: gw系 + `-fpcN` サフィックス → サフィックス除去して `cmdb_ci_ip_router` で CI 照合
- **B**: `fpcN` 単体（ホスト名なし） → 無視
- **C**: gw系 + `-reN` サフィックス → サフィックス除去して `cmdb_ci_ip_router` で CI 照合
- **D**: IPアドレス形式 node → `cmdb_ci` の `u_private_ip_address` / `u_public_ip_address` で CI 照合

## 実行例（alertchk）

```bash
# em_alert 全件チェック（サマリー表示）
source ./setup.sh && python3 alertchk/check_alerts.py

# NG項目の詳細表示
source ./setup.sh && python3 alertchk/check_alerts.py --output detail

# 変換後ソースで絞り込み
source ./setup.sh && python3 alertchk/check_alerts.py --source iMark_AWS --output detail

# sys_id を指定して1件表示
source ./setup.sh && python3 alertchk/get_alert.py <sys_id>
source ./setup.sh && python3 alertchk/get_alert.py <sys_id> --json

# CI未バインドアラート調査（ファイル名は ci_unbound_alerts_YYYYMMDD.xlsx で自動生成）
source ./setup.sh && python3 alertchk/check_ci_unbound.py

# ファイル名を明示指定する場合
source ./setup.sh && python3 alertchk/check_ci_unbound.py --file tmpdir/ci_unbound_alerts_custom.xlsx

# 日付範囲絞り込み（6/1〜6/18 等）
source ./setup.sh && python3 alertchk/check_ci_unbound.py --query "sys_created_on>=2026-06-01^sys_created_on<2026-06-19" --file tmpdir/ci_unbound_alerts_20260601_20260618.xlsx

# CMDB照合スキップ（高速確認用）
source ./setup.sh && python3 alertchk/check_ci_unbound.py --no-cmdb

# 件数制限（テスト用）
source ./setup.sh && python3 alertchk/check_ci_unbound.py --limit 2000
```

## 実行例（cichk）

```bash
# 全テーブル 設定チェック（サマリー＋カテゴリ別集計）
source ./setup.sh && python3 cichk/check_ci_bindings.py

# NG/WARN 詳細表示
source ./setup.sh && python3 cichk/check_ci_bindings.py --output detail

# sa_event_rule のみチェック（主要CIバインドルール）
source ./setup.sh && python3 cichk/check_ci_bindings.py --table sa_event_rules

# u_transformation_rule のみ / カテゴリ絞り込み
source ./setup.sh && python3 cichk/check_ci_bindings.py --table transformation_rules
source ./setup.sh && python3 cichk/check_ci_bindings.py --table transformation_rules --category ログ変換

# JSON出力
source ./setup.sh && python3 cichk/check_ci_bindings.py --output json > tmpdir/ci_bindings_check.json

# CI バインディング仕様書を Excel で出力（全テーブル）
source ./setup.sh && python3 cichk/get_ci_bindings.py --output excel --file tmpdir/ci_binding_spec.xlsx

# JSON 出力（標準出力）
source ./setup.sh && python3 cichk/get_ci_bindings.py > ci_bindings.json

# sys_id を指定して1件表示（sa_event_rule がデフォルト）
source ./setup.sh && python3 cichk/get_ci_binding.py <sys_id>
source ./setup.sh && python3 cichk/get_ci_binding.py <sys_id> --json
# em_mapping_rule を参照する場合
source ./setup.sh && python3 cichk/get_ci_binding.py --table em_mapping_rule <sys_id>
```

## 実行例（eventchk）

```bash
# em_event 全件チェック（サマリー表示）
source ./setup.sh && python3 eventchk/check_events.py

# NG項目の詳細表示
source ./setup.sh && python3 eventchk/check_events.py --output detail

# 特定ソースだけ絞り込み
source ./setup.sh && python3 eventchk/check_events.py --source Zabbix --output detail

# 件数上限指定・クエリ絞り込み
source ./setup.sh && python3 eventchk/check_events.py --limit 200 --query "state=ready"

# JSON出力
source ./setup.sh && python3 eventchk/check_events.py --output json > result.json

# sys_id を指定して1件表示
source ./setup.sh && python3 eventchk/get_event.py <sys_id>
source ./setup.sh && python3 eventchk/get_event.py <sys_id> --json

# sys_id を指定して Athena (snow_prd.v_em_event) から1件表示
source ./setup.sh && python3 eventchk/get_event_athena.py <sys_id>

# em_event からレコード取得（生JSON）
python get_events.py --table em_event --limit 50 --query "state=ready"
```

## 実行例（zabbixcibind）

```bash
# イベントルール・CMDB・em_event・em_alert・em_binding_device_map を一括調査
source ./setup.sh && python3 zabbixcibind/diagnose_ci_bind.py

# テストイベント投入（node=空, additional_info.name=test-interface3-ootb）→ CI バインド確認
source ./setup.sh && python3 zabbixcibind/send_test_event.py

# ペイロード確認のみ（投入しない）
source ./setup.sh && python3 zabbixcibind/send_test_event.py --dry-run

# 処理待機時間を変更（デフォルト20秒）
source ./setup.sh && python3 zabbixcibind/send_test_event.py --wait 30

# イベントルールの identification_rules を変更（dry-run で確認）
source ./setup.sh && python3 zabbixcibind/update_event_rule.py --dry-run

# 実際に変更
source ./setup.sh && python3 zabbixcibind/update_event_rule.py
```

## check_events.py オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--limit N` | 0（全件） | 最大取得件数。0で全件ページネーション取得 |
| `--query` | "" | sysparm_query フィルタ条件 |
| `--source` | "" | source フィールドで絞り込み |
| `--output` | summary | summary / detail / json |
| `--show-ok` | off | detail 時に OK 項目も表示 |

## 対応データソース

### eventchk/validators.py（em_event 側）

| ID | em_event source 値 | severity 許容値 | 備考 |
|---|---|---|---|
| 1-1 | `CloudWatchLogs` | 1/2/3/4/5 | |
| 1-2 | `RDS` | 1/2/3/5 | マイナー(3)も許容（INSUFFICIENT_DATA 等） |
| 1-3 | `HIOS(AWS)` | 2/4 | |
| 1-4 | `CloudWatchLogs(HIOS)` | 1/2/3/4/5 | metric_name はチェック対象外 |
| 1-5 | `Trap From Enterprise 119` | 1/3 | additional_info の OID `.300.6` で識別 |
| 1-6 | `Dead Letter Queue` | 2/5 | |
| 2-1 | `Trap From Enterprise 119` | 1/2/3/4 | additional_info の OID `.300.1` で識別 |
| 2-2 | `SNMPv2 Generic Trap` | — | severity は Event→Alert 処理時に設定 |
| HW-674 | `Trap From Enterprise 674` | — | Dell iDRAC。severity は Event→Alert 処理時に設定 |
| HW-3375 | `Trap From Enterprise 3375` | — | F5 BIG-IP。node は構造的に空 |
| HW-22610 | `Trap From Enterprise 22610` | — | A10 Networks（2026-06-16 追加） |
| 2-3 | `NNMi` | 2/5 | HighImpact→重要(2), NoImpact→情報(5) |
| 2-4,2-5 | `HIOS(SV)` | 2/3/4/5 | |
| 3-1 | `Zabbix` | 0/1/2/3/4/5 | |
| 3-3 | `syslog` | 1/2 | |
| — | `PRTG` | 1/2/4/5 | |
| — | `キャリア障害(光回線)` | 3 | |
| — | `キャリア障害(GASフィルター後)` | 3 | |
| — | `キャリア障害(type A)` | 3 | |
| — | `Triplエラー` | 3 | |
| — | `Downdetector` | 3/4 | |
| — | `JPIX` | 3 | |
| — | `ウェザーニューズ` | 3 | |
| — | `EMSelfMonitoring` | 1/2/3/4/5 | |

### alertchk/alert_validators.py（em_alert 側）

em_event → イベントルール → em_alert 変換後の source 値で識別。

| em_alert source 値 | u_type_category | severity 許容値 | 備考 |
|---|---|---|---|
| `CloudWatchLogs` | AWS | 1/2/3/4/5 | |
| `CloudWatchLogs(HIOS)` | AWS | 1/2/3/4/5 | |
| `HIOS(AWS)` | AWS | 2/4 | |
| `RDS` | AWS | 1/2/3/5 | |
| `Dead Letter Queue` | AWS | 2/5 | |
| `iMark_AWS` | AWS | 1/3 | |
| `iMark_SV` | SV | 1/2/3/4 | |
| `HW監視` + resource=`Dell iDRAC` | SV | 3/4/5 | |
| `HW監視` + resource=`BIG-IP` | SV | 3 | node は構造的に空 |
| `HW監視` + resource=`A10` | SV | 3/4 | |
| `NNMi` | NW | 2/5 | |
| `HIOS(SV)` | SV | 2/3/4/5 | |
| `Zabbix` | NW | 0/1/2/3/4/5 | |
| `syslog` | NW | 1/2 | u_alert_type=【NW】syslog監視。u_monitoring_item_number は全件空 |
| `PRTG` | NW | 1/2/4/5 | |
| `キャリア障害(光回線)` | NW | 3 | |
| `キャリア障害(GASフィルター後)` | NW | 3 | |
| `キャリア障害(type A)` | NW | 3 | |
| `Triplエラー` | NW | 3 | |
| `Downdetector` | その他 | 3/4 | |
| `JPIX` | NW | 3 | |
| `ウェザーニューズ` | その他 | 3 | |
| `EMSelfMonitoring` | その他 | 1/2/3/4/5 | |
| 業連メール / DDoS / Mackerel 等 17種 | — | — | メールからAlertへの変換（em_event を経由しない）|

## 認証フロー

1. `SNOW_CLIENT_ID` / `SNOW_CLIENT_SECRET` が `.env` にあればそのまま使用
2. 空の場合は `SNOW_SECRET_NAME` で指定された AWS Secrets Manager からキーを取得（シークレットの JSON キー名は `OAuthToken`/`OAuthSecret` と `ClientID`/`ClientSecret` の両方に対応。インスタンスによってキー名が異なるため）
3. `snow_client.get_token()` で OAuth アクセストークンを発行

## 環境変数

| 変数 | 説明 |
|---|---|
| `SNOW_BASE_URL` | ServiceNow インスタンスの URL |
| `SNOW_CLIENT_ID` | OAuth クライアント ID（省略可） |
| `SNOW_CLIENT_SECRET` | OAuth クライアントシークレット（省略可） |
| `SNOW_SECRET_NAME` | AWS Secrets Manager のシークレット名 |
| `AWS_TOKEN` | `setup.sh` で使う MFA トークン等 |

## 依存ライブラリ

- `boto3` — AWS SDK (Secrets Manager / Athena アクセス)
- `requests` — HTTP クライアント
- `python-dotenv` — `.env` 読み込み
- `openpyxl` — Excel ファイル生成（障害フォロー票出力用）

## チェック結果 em_event（2026-06-16 時点）

対象: biglobeprod 全件 25,879件。詳細は `tmpdir/イベントテーブルまとめ_2026-06-16.xlsx` を参照。

| 区分 | 件数 | 前回（2026-06-09 nonprod） |
|---|---:|---:|
| OK | 25,699件 | 15,281件 |
| NG（仕様不一致） | 155件 | 4,749件 |
| 不明ソース（仕様書未定義） | 25件 | 4,759件 |

残課題:
- `CloudWatchLogs` metric_name 変数未展開 22件 — `<'{Trigger[MetricName"]}':UNKNOWN>"` がそのまま残留 → 変換スクリプト修正
- `Trap From Enterprise 119` (iMark(AWS)) node/message_key/severity 空 132件 — agent_address=192.168.53.210 からのトラップのみ。イベントルール（sa_event_rule）の設定確認が必要
- `Zabbix` metric_name 空 1件
- UNKNOWN 25件 — `業連メール`・`工事連絡` 等が em_event にも存在するケースがある（alertchk 側では「メールからAlertへの変換」として OK 扱い済み）

## チェック結果 em_alert

### 全件（2026-06-11 時点）

対象: biglobeprod 全件 100,460件。詳細は `tmpdir/イベントテーブルまとめ_2026-06-11.xlsx` を参照。

| 区分 | 件数 |
|---|---:|
| OK | 96,157件 |
| NG（仕様不一致） | 4,303件 |
| 不明ソース | 0件 |

### 4/1〜6/18（2026-06-18 時点）

対象: biglobeprod 85,876件。詳細は `tmpdir/アラートチェックまとめ_20260618.xlsx` を参照。

| 区分 | 件数 |
|---|---:|
| OK | 81,607件 |
| NG（仕様不一致） | 4,269件 |
| 不明ソース | 0件 |

### 6/1〜6/18（2026-06-18 時点）

対象: biglobeprod 43,800件。

| 区分 | 件数 |
|---|---:|
| OK | 43,738件 |
| NG（仕様不一致） | 62件 |
| 不明ソース | 0件 |

### syslog アラート フィールド組み合わせ分析（2026-06-30 時点）

対象: biglobeprod、4/1以降の source=syslog アラート 16,989件（`datakaiseki/syslog_combo.py`）。

| u_monitoring_type | u_monitoring_item_number | u_alert_type（アラートタイプ） | u_type_category | 件数 |
|---|---|---|---|---:|
| syslog | (空) | 【NW】syslog監視 | NW | 16,989 |

- 組み合わせ 1種類のみ。全件統一されている
- アラートタイプは標準 `type` フィールドではなくカスタムフィールド `u_alert_type` に格納（`type` は全件空）
- `u_monitoring_item_number` は全件空

### NG残置（意図的）

- `Zabbix` u_type_category — 「その他」（仕様は「NW」）→ イベントルール修正が必要
- `Zabbix` metric_name — 空のアラートが一部存在 → イベントルール修正が必要
- `Triplエラー` 10件 — description/additional_info が 4,000文字超過（最大 13,825文字）→ 変換スクリプト修正
- `HIOS(AWS)` — message_key が 1,024文字超過 → 変換スクリプト修正

## CI バインディング / アラート変換ルール チェック結果（2026-06-12 時点）

仕様書: `tmpdir/ci_binding_spec.xlsx`（本番環境から自動生成、9シート）

| 区分 | 件数 | OK | NG | WARN |
|---|---:|---:|---:|---:|
| matchRule（CIバインディング） | 8 | 8 | 0 | 0 |
| em_mapping_rule（フィールドマッピング） | 62 | 61 | 1 | 0 |
| u_transformation_rule（アラート変換ルール） | 342 | 310 | 0 | 32 |

課題:
- `Dynatrace Metrics Process Binding`（em_mapping_rule）— `from_field` / `to_field` ともに空（設定不完全）
- `u_transformation_rule` WARN 32件 — 非アクティブルール（無効化済みの抑止・テスト・旧ルール等）
- `u_transformation_rule` order値重複 83件 — 同一 order での処理順が不定

matchRule の CIバインディング対象ソース: Splunk, vmwVC, oraEM4Traps, HPOMWIN（旧世代ルール）

## CI未バインドアラート 分析結果（2026-06-18 時点）

対象: `em_alert` テーブルの `cmdb_ciISEMPTY`（CI未バインド）レコード。

| 期間 | 詳細レポート | 総取得 | 除外 | 要対応 |
|---|---|---:|---:|---:|
| 全件（2026-06-17） | `tmpdir/ci_unbound_alerts_20260617.xlsx` | 38,334件 | 21,443件 | 16,891件 |
| 4/1〜6/18（2026-06-18） | `tmpdir/ci_unbound_alerts_20260401_20260618.xlsx` | 31,526件 | 13,369件 | 18,157件 |
| 6/1〜6/18（2026-06-18） | `tmpdir/ci_unbound_alerts_20260601_20260618.xlsx` | 9,792件 | 6,138件 | 3,654件 |

※ Zabbix/CloudWatchLogs/HIOS(SV)/HIOS(AWS) の各シート末尾に「疑義CI CMDB照合表」（ノード別 CMDB存在確認）を掲載。

> **変更（2026-06-18）**: HIOS(AWS) を除外条件から削除。207ノード中 206件 CMDB登録済みのため、CIバインドルール追加で対応可能と判断。

### 除外条件

| 除外理由 | 条件 |
|---|---|
| iMark_AWS(Servicekanshi) | source=iMark_AWS かつ node に Servicekanshi を含む |
| キャリア障害系 | source が「キャリア障害」で始まる |
| Zabbix正常性確認(ハートビート) | source=Zabbix かつ node に test-servicenow を含む |
| 業連メール | 業務連絡メール自動転送 |
| DDoS | DDoS検知システム（Arbor）通知 |
| JPIX | IX系通知 |
| ウェザーニューズ | 気象情報通知 |
| Downdetector | 外部サービス死活監視 |
| WebAI | GAS（CareerMailChecker）エラー通知（問題なし確認済み） |
| Service Health Dashboard Alarm | AWS SHD フィード廃止通知（実障害通知なし） |
| Email | バウンスメール通知（問題なし確認済み） |
| DeepField/Arbor vSP | Arbor DDoS Mitigation通知（DDoSと同性質） |
| ServiceNowテストメールアラート | テスト用メール |
| EMSelfMonitoring | EM自己監視（問題なし確認済み） |
| bousai | 防災情報メール転送（問題なし確認済み） |
| ServiceNow UATテストメールアラート | UAT環境テストメール |
| Mackerel | 対応不要（CMDB未登録・対応優先度なし） |
| ExpressList表示対象外 | 業連メールと同様のメール転送（問題なし確認済み） |
| 工事連絡 | 工事連絡メール転送（問題なし確認済み） |

### 要対応 source 別分析結果

| 優先度 | source | 未バインド原因 | 対応方針 |
|---|---|---|---|
| **高** | Zabbix | node にIF名混入・ssap/htap CMDB未登録・iMarkN外部URL | node正規化ルール追加・CMDB登録・iMarkN除外検討 |
| **高** | CloudWatchLogs | typeが全件空・CIバインドルール未設定 | em_rule_xml に CloudWatchLogs ソース向けルール追加 |
| **高** | HIOS(SV) | type/resource全件空・CIバインドルール未設定（severity全件重要） | HIOS(SV)ソース向けCIバインドルール追加・w19ad01 CMDB登録 |
| **高** | CloudWatchLogs(HIOS) | type全件空・BO-CAP_v6 CMDB未登録 | CIバインドルール追加・BO-CAP_v6 CMDB登録 |
| **高** | HIOS(AWS) | CIバインドルール未設定。207ノード中 206件CMDB登録済み | CIバインドルール追加のみで対応可 |
| 方式調査 | HW監視 | node=trapSV集約（CMDB未登録）。実機FQDNはadditional_info.alertSystemFQDNに存在 | u_transformation_rule で alertSystemFQDN を node に展開 |
| 方式調査 | syslog | node に-fpcN/-reN サフィックス混入・IPアドレスノード・pts系 | 詳細は「syslog CI未バインド分析結果」参照 |
| S-in後対応 | Triplエラー | node/type/resource全件空。PandoraFMS、full_textに実機名あり | u_transformation_rule で full_text からnode展開 |
| **中** | RDS | type/resource全件空・CMDB登録済み | RDSソース向けCIバインドルール設定 |
| **中** | iMark_SV | node=集約サーバ（trapSV/servicekansi）・変換ルール未設定 | additional_info から実機ノード名展開 |
| 低 | SNMPv1 Generic Trap | bglb系はCMDB登録済み・IPアドレスノードは未登録 | bglb系CIバインド設定 |
| 低 | AWS maintenance | AWSメンテナンス通知（sid=bsd3369） | sid→node展開またはCI無し処理検討 |
| 低 | SNMPv2 Generic Trap | IPアドレスノードがCMDB名と不一致 | CMDB登録またはCIなし処理 |
| 低 | (空) | sourceフィールド空。変換ルール設定漏れの可能性 | 該当アラートのadditional_info確認 |

### CMDB照合結果サマリー（疑義CI CMDB照合表より）

- **HIOS(AWS)**: 207ノード中 206件CMDB登録済み → **CIバインドルール追加のみで対応可**
- **CloudWatchLogs**: 170ノード中 142件CMDB登録済み → **CIバインドルール追加のみで対応可**
- **HIOS(SV)**: 6ノード中 3件登録済み・w19ad系未登録 → **w19ad系 CMDB登録 + ルール追加**
- **Zabbix**: 1,974ノード中 343件CMDB登録済み。残り1,631件はIF名混入・CMDB未登録等
- **syslog**: gw系はCMDB登録済み（IPルーター）・IPアドレスノードは未登録（詳細は「syslog CI未バインド分析結果」参照）
- **HW監視**: trapSV未登録・alertSystemFQDNのbgeb系はCMDB登録済み
- **RDS**: big/bsd系DBインスタンス全件登録済み → **CIバインドルール追加のみで対応可**

## syslog CI未バインド分析結果（2026-06-29 時点）

対象: biglobeprod `em_alert` source=syslog / 4月以降 16,912件。詳細は `datakaiseki/syslog_alerts_20260629.xlsx` を参照。

| 区分 | 件数 |
|---|---:|
| CI バインド済み | 14,009件 |
| CI 未バインド | 2,903件 |

### CI未バインド 対処パターン別内訳

| 対処パターン | 件数 | CI特定 | 内容 |
|---|---:|---|---|
| A（FPC除去） | 1,837件 | あり | gw系 `-fpcN` 除去 → `cmdb_ci_ip_router` でCI特定済み |
| B（無視） | 96件 | 無視 | `fpcN` 単体ノード（ホスト名なし）→ 無視 |
| C（RE除去） | 98件 | あり | gw系 `-reN` 除去 → `cmdb_ci_ip_router` でCI特定済み |
| D（IP照合） | 471件 | あり | IPアドレスノード → `cmdb_ci` IP フィールドでCI特定済み |
| D（IP照合） | 391件 | **なし** | IPアドレスノード `10.80.253.118` → CMDB未登録 |
| 対処なし | 10件 | — | `pts822-osk06`(6件) / `pts891-osk04`(4件) ※4/1のみ・対応済み扱い |

### 残課題

| node | 件数 | 原因 | 対応方針 |
|---|---:|---|---|
| `10.80.253.118` | 391件 | CMDBに `u_private_ip_address` / `u_public_ip_address` で未登録 | 対応機器を特定してCMDBに登録し既存CIに紐付け |
| `pts822-osk06` / `pts891-osk04` | 10件 | 2026-04-01 のみ発生。以降はCI「あり」→ CIバインドルールが4/1後に設定済み | **対応済み**（4/1当日の過渡的な未バインド） |

## Zabbix CI バインド調査結果（biglobedev、2026-07-16 時点）

対象: `dscy_router_interface`（test-interface3-ootb）を `additional_info.name` で CI バインドする方式の検証。

### 判明事項

| 項目 | 内容 |
|---|---|
| 使用イベントルール | `Zabbix_アラート作成ルール monotest 版 Device Mapping version`（order=300, bind_type=2） |
| ci_type | `dscy_router_interface` |
| identification_rules | `attribute=name / value=node`（イベントの node フィールドで dscy_router_interface.name を検索） |
| node ベース CI バインド | **成功**。`dscy_router_interface` の Identification Rule を Independent 化することで `node` フィールドによる CI バインドが動作 |
| additional_info.name ベース | **未解決**。IRE（Identification Rule Engine）は `value="additional_info.name"` という JSON パス参照をサポートしていない。`No conditions found for matching` となる |

### dscy_router_interface の Identification Rule 設定変更（2026-07-15）

CI Class Manager → `dscy_router_interface` の Identification Rule を **Dependent → Independent** に変更することで CI バインドが成功するようになった。

- **変更前（Dependent）**: Hardware（cmdb_ci_hardware）への上位チェーンを要求。Zabbix イベントには Hardware 情報がないため識別失敗
- **変更後（Independent）**: `name` 属性のみで識別可能。CI バインド成功

### additional_info.name を使う方式（未解決）

IRE の `identification_rules.value` フィールドはイベントテーブルの列名（`node`, `resource` 等）のみ受け付けるため、`additional_info` の JSON サブフィールドへの直接参照はできない。

試した方法と結果:
- `value: "additional_info.name"` → No conditions found for matching
- `event_data.additionalInfoFields` に `name` を追加後も変化なし

代替アプローチ（未実施）:
- bind_type=1（CI field match）で `event_field` に `additional_info.name` が使えるか試す
- `event_data.rawFields` の node エントリで Transform 式を使って `additional_info.name` を node に補完する
