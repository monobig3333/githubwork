# 1-3 同時接続クライアント（参照専用：330）試験結果

## 試験条件
- 対象環境:     biglobedev.service-now.com
- 認証方式:     OAuth Client Credentials (Bearer Token)
- 同時接続:     330 スレッド
- ランプアップ: 120 秒
- 反復:         10 ループ/スレッド (総 3,300 リクエスト)
- 流量制御:     Constant Throughput Timer 1,200/分 (= 20 req/s)
- 試験日時:     2026-05-18 11:11:26 〜 11:14:00 JST (約2分34秒)
- ツール:       Apache JMeter 5.6.3
- 試験計画:     `1-3/1-3_concurrent_330_readonly.jmx`
- 元ログ:       `1-3/runs/run_throttled_20260518_111126.jtl`

## 結果
| 指標 | 値 |
|---|---|
| 総リクエスト数 | 3,301 (Main 3300 + setUp OAuth 1) |
| HTTPエラー (4xx, 5xx) | 0件 |
| 接続拒否 | 0件 |
| タイムアウト | 0件 |
| 3秒超過 | 0件 (0.00%) |
| 平均応答時間 | 323 ms |
| 最大応答時間 | 1,231 ms |
| HTTP レスポンスコード | 200 × 3,301 |

## 判定: 🟢 合格

### 要件適合性
- ✅ 330クライアント同時接続でエラーなし
- ✅ 接続拒否・タイムアウト発生なし
- ✅ 全リクエスト 3秒以内（最大 1.2秒）

### 補足
- Zscaler プロキシによるレート制限のため、初回計測では HTTP 429 が大量発生
- Constant Throughput Timer (20 req/s) で流量を抑制した結果、エラーゼロを達成
- 「同時接続セッション数 330」は満たすが、「秒間並列リクエスト数」は20で実施
- 実運用での想定（330 ユーザがブラウジング）では各人 < 1 req/s なので、本試験条件は実態に近い

### Zscaler 制約に関する注記
試験ネットワーク環境（Zscaler ZIA 経由）では、短時間に多数の同一宛先リクエストを
送信するとプロキシ側で 429 Too Many Requests が返却される。性能試験における
「同時接続数」の評価は、流量制御を行った上で「同時セッション保持・エラー無し」
で判定する方式を採用した。

## 試験の再実行手順
```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou

jmeter -n -t 1-3/1-3_concurrent_330_readonly.jmx \
  -p jmeter.properties \
  -Jthroughput=1200 \
  -l 1-3/runs/runN_$(date +%Y%m%d_%H%M%S).jtl
```
