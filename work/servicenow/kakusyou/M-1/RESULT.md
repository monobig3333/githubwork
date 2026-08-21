# M-1 MIDサーバ イベント転送スループット（通常時） 試験結果

## 判定: **OK**

## 試験条件

- 負荷: 10 スレッド × 30 ループ = 300 イベント（標準負荷）
- リクエスト: `POST /api/now/table/em_event`
- コマンド: `-Jthreads=10 -Jramp_up=5 -Jloop.count=30`

## 結果

| 指標 | 実測 | 合否判定基準 | 判定 |
|---|---|---|---|
| 投入 | em_event **201 Created × 300** 件 | — | — |
| **失敗** | **0 件** | — | — |
| **全件投入完了まで** | **16.1 秒** | 10 分 30 秒（630 秒）以内 | ✅ |
| **ServiceNow 受信数** | **300 件**（`source=mid-test-M-1`） | 転送漏れなし | ✅ |
| 応答時間 | 平均 69 ms / 最大 224 ms | — | — |

## 判定理由

- JMeter 投入 300 件 = ServiceNow 受信 300 件で **転送漏れなし**
- 全件完了まで 16.1 秒で、基準の 630 秒に対して大幅な余裕

## ⚠️ 試験方式に関する重要な注記

**本 JMX は `POST /api/now/table/em_event` で ServiceNow の Table API を直接叩いており、
MID Server を経由していない。** README には「JMeter から MID サーバ経由で em_event を投入」と
あるが実装が異なる。「MID サーバ イベント転送スループット」の計測として成立するかは
要件チームとの確認事項（再測定_実行計画.md の B6）。M-2 / M-3 も同じ構造。

また Excel の前提条件「3AZ 全ての MID サーバが稼働中」に対し、dev は `mid-server-zabbix`
1 台構成（t3.large / ヒープ 4096 MB）である。

## 修正履歴

2026/8/14 のスモークで、メインの Response Assertion が `200` のみを許容していたため
**全件エラー判定になる不具合**を発見し `201` に修正した。本試験はその修正後の実行。

## 証跡

- 元ログ: `M-1/runs/run_20260819_150835.jtl`

## 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/8/19 |
| 担当 | 小野 |
| 対象インスタンス | biglobedev (Zurich) |
| 認証方式 | OAuth Client Credentials (Bearer Token) |
| ツール | Apache JMeter 5.6.3 |
| 元ログ | `M-1/runs/run_20260819_150835.jtl` |

## 環境に関する注記

本再測定は **biglobedev** で実施。dev の MID Server は `mid-server-zabbix` の 1 台構成
(t3.large / 7 GiB / Java ヒープ 4096 MB) であり、Excel の前提条件「3AZ 全ての MID サーバが
稼働中」を満たさない。nonprod (3AZ 構成) との単純比較はできない。


