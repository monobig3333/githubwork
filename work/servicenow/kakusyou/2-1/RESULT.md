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
