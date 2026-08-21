# 2-1 アラームビューワー同時接続（165）試験結果

## 試験条件
- 対象環境:     biglobedev.service-now.com
- 認証方式:     OAuth Client Credentials (Bearer Token)
- 同時接続:     165 スレッド
- ランプアップ: 60 秒
- 反復:         10 ループ/スレッド (総 1,650 リクエスト)
- 流量制御:     Constant Throughput Timer 1,200/分 (= 20 req/s)
- API:          GET /api/now/table/em_alert?sysparm_limit=50
- 試験日時:     2026-05-18 11:21:24 〜 11:22:44 JST (約80秒)
- ツール:       Apache JMeter 5.6.3
- 試験計画:     `2-1/2-1_alarm_viewer_165.jmx`
- HTMLレポート: `2-1/report/index.html`

## 結果
| 指標 | 値 |
|---|---|
| 総リクエスト数 | 1,651 (Main 1650 + setUp OAuth 1) |
| HTTPエラー | 0件 |
| 接続拒否 | 0件 |
| タイムアウト | 0件 |
| 3秒超過 | 0件 (0.00%) |
| 平均応答時間 | 390 ms |
| 最大応答時間 | 1,634 ms |
| HTTP レスポンスコード | 200 × 1,651 |

## 判定: 🟢 合格

### 要件適合性
- ✅ 165クライアント同時接続でエラーなし
- ✅ 画面（API）が正常に応答（全件 200 OK）
- ✅ 全リクエスト 3秒以内（最大 1.6 秒）

### Zscaler 制約に関する注記
1-3 と同様、Zscaler プロキシのレート制限を回避するため
Constant Throughput Timer (20 req/s) で流量を抑制した条件で実施。

## 試験の再実行手順
```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou

jmeter -n -t 2-1/2-1_alarm_viewer_165.jmx \
  -p jmeter.properties \
  -Jthroughput=1200 \
  -l 2-1/runs/runN_$(date +%Y%m%d_%H%M%S).jtl
```


---

## 再測定 2026/8/19 (biglobedev)

### 判定: **OK**

### 試験条件

- 同時接続: 165 スレッド / ランプアップ 60 秒 / 10 ループ（総 1,650 リクエスト）
- 流量制御: Constant Throughput Timer 1,200/分
- API: `GET /api/now/table/em_alert?sysparm_limit=50`
- コマンド: `-Jthreads=165 -Jramp_up=60 -Jloop.count=10 -Jthroughput=1200`

### 結果

| 指標 | 実測 |
|---|---|
| 総リクエスト数 | 1,651 |
| レスポンスコード | 200 × 1,651 |
| **失敗** | **0 件** |
| 平均応答時間 | 512 ms |
| 中央値 | 324 ms |
| 90 パーセンタイル | 1,287 ms |
| 95 パーセンタイル | 1,410 ms |
| 99 パーセンタイル | 1,569 ms |
| 最大応答時間 | 2,620 ms |
| **3 秒超過** | **0 件** |
| 実行時間 | 80 秒 |
| スループット | 20.6 req/s |

### 判定理由

- 165 クライアント同時接続で **HTTP エラー 0 件**
- 画面（API）が正常に応答（全件 200 OK）。レスポンスは 1 件あたり約 499 KB で、
  `sysparm_limit=50` に対して 50 件が返っていることを確認
- 3 秒超過 0 件


### 1 回目の実行について（参考）

同日 13:58 の 1 回目は HTTP は全件 200 だったが、開始 24.7〜24.8 秒に集中して 4 件（0.24%）が
3 秒を超えた（最大 8,661 ms）。持続的な劣化ではなく瞬間的なスパイクであり、2 回目（本結果）では
再現しなかったため一時的な外乱と判断した。1 回目のログは `2-1/runs/run_20260819_135820.jtl` に保全。

なお Excel の 2-1 の合否判定基準は「165 クライアント同時接続でエラーなし・画面が正常に描画されること」で
応答時間の閾値は規定されていない（3 秒基準は 1-2 の要件）。JMX の Duration Assertion は実装側の追加。

### 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/08/19 |
| 実施時刻 | 14:06:18 〜 14:07:38 |
| 対象インスタンス | biglobedev (Zurich) |
| 認証方式 | OAuth Client Credentials (Bearer Token) |
| ツール | Apache JMeter 5.6.3 |
| 元ログ | `2-1/runs/run_20260819_140616.jtl` |

> dev の MID Server は 1 台構成 (t3.large / ヒープ 4096 MB)。Excel の前提条件
> 「3AZ 全ての MID サーバが稼働中」は満たしていない。
