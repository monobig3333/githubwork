# 3-1 ワークフロー並列実行（100プロセス） 試験結果

## 判定: **OK**

## 試験条件

- 並列数: 100 スレッド / ランプアップ 10 秒 / 1 ループ
- リクエスト: `POST /api/now/table/incident`（インシデントを並列起票し、契機となるワークフローを走らせる）
- 許容レスポンス: 200 または 201
- コマンド: `-Jthreads=100 -Jramp_up=10 -Jloop.count=1`

## 結果

| 指標 | 実測 |
|---|---|
| 総リクエスト数 | 101（setUp OAuth 1 + 起票 100） |
| レスポンスコード | 200 × 1（OAuth）、**201 Created × 100** |
| **失敗** | **0 件** |
| 平均応答時間 | 236 ms |
| 中央値 / 最大 | 215 ms / 593 ms |
| 95 パーセンタイル | 351 ms |
| 3 秒超過 | 0 件 |
| 並列実行の広がり | 11.0 秒（ramp_up 10 秒指定） |

## 判定理由

- **100 プロセスが並列実行され、全件 201 Created**
- プロセス間の干渉・エラーは発生していない
- 応答時間も平均 236 ms と安定

## 試験方式についての注記

旧 README には トリガ URL `/api/sn_ind_pmpf/workflow/trigger` を「サンプル」とする記載があったが、
JMX の実装は既に `POST /api/now/table/incident`（インシデント並列起票方式）に差し替わっていた。
2026/7/31 に確認し README を実態に合わせて修正済み。

**本試験は対象インスタンスに実際にインシデントを 100 件作成する。** 作成レコードは
`short_description` が `[3-1] perf test parallel workflow` で始まる。

## 証跡

- 元ログ: `3-1/runs/run_20260819_150657.jtl`
- HTML レポート: `3-1/report_20260819/index.html`

## 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/8/19 |
| 担当 | 小野 |
| 対象インスタンス | biglobedev (Zurich) |
| 認証方式 | OAuth Client Credentials (Bearer Token) |
| ツール | Apache JMeter 5.6.3 |
| 元ログ | `3-1/runs/run_20260819_150657.jtl` |

## 環境に関する注記

本再測定は **biglobedev** で実施。dev の MID Server は `mid-server-zabbix` の 1 台構成
(t3.large / 7 GiB / Java ヒープ 4096 MB) であり、Excel の前提条件「3AZ 全ての MID サーバが
稼働中」を満たさない。nonprod (3AZ 構成) との単純比較はできない。


