# M-2 MIDサーバ 転送スループット（最大負荷 30,000件/10分） 試験結果

## 判定: **OK**

## 試験条件

- 負荷: 50 スレッド / ランプアップ 10 秒 / duration 600 秒
- 流量制御: Constant Throughput Timer 3,000/分（= 50 件/秒）
- リクエスト: `POST /api/now/table/em_event`（`source=mid-test-M-2`）
- コマンド: `-Jthreads=50 -Jramp_up=10 -Jduration.sec=600`

## 結果

| 指標 | 実測 | 合否判定基準 | 判定 |
|---|---|---|---|
| 投入 | em_event **201 Created × 29,986** 件 | — | — |
| **失敗** | **0 件** | — | — |
| **ServiceNow 受信数** | **29,986 件** | 全イベントが転送されること | ✅ |
| **差分（欠損）** | **0 件** | 処理漏れ・スキップなし | ✅ |
| 実効レート | **49.9 件/秒**（目標 50） | — | — |
| 実行時間 | 601 秒 | — | — |
| 応答時間 | 平均 136 ms / 中央 118 ms / 95%ile 234 ms / 最大 2,836 ms | — | — |
| 3 秒超過 | 0 件 | — | — |

## 判定理由

- **投入 29,986 件 = ServiceNow 受信 29,986 件**（`source=mid-test-M-2` でカウント）。欠損ゼロ
- 10 分間を通じて 49.8〜50.2 件/秒で安定し、要件レート（30,000 件/10 分 = 50 件/秒）を達成
- 29,986 件は duration 打ち切りによる端数（30,000 件に対し 14 件不足）

## 修正履歴

2026/8/14 のスモークで、HeaderManager に `Authorization: Bearer ...` が **2 行**入っており、
ServiceNow 前段（`snow_adc`）が重複ヘッダを **400 Bad Request** で拒否する不具合を発見・修正した。
あわせて Constant Throughput Timer をハードコード（3000.0）から `${__P(throughput,3000)}` に変更
（既定値は 3000 のままで条件に影響なし）。本試験は修正後の実行。

## ⚠️ 試験方式に関する注記

M-1 と同様、本 JMX は Table API を直接叩いており **MID Server を経由していない**（B6）。
dev の MID は 1 台構成のため、Excel の前提条件「3AZ 全ての MID サーバが稼働中」も満たしていない。

## 証跡

- 元ログ: `M-2/runs/run_20260821_100345.jtl`

## 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/8/21 |
| 担当 | 小野 |
| 対象インスタンス | biglobedev (Zurich) |
| 認証方式 | OAuth Client Credentials (Bearer Token) |
| ツール | Apache JMeter 5.6.3 |
| 元ログ | `M-2/runs/run_20260821_100345.jtl` |

## 環境に関する注記

本再測定は **biglobedev** で実施。dev の MID Server は `mid-server-zabbix` の 1 台構成
(t3.large / 7 GiB / Java ヒープ 4096 MB) であり、Excel の前提条件「3AZ 全ての MID サーバが
稼働中」を満たさない。nonprod (3AZ 構成) との単純比較はできない。


