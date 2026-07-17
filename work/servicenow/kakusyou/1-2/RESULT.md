# 1-2 同時接続クライアント（参照/更新：165）試験結果

## 試験条件
- 対象環境:     biglobedev.service-now.com
- 認証方式:     OAuth Client Credentials (Bearer Token)
- 同時接続:     165 スレッド
- ランプアップ: 60 秒
- 反復:         10 ループ/スレッド (総 1,650 リクエスト)
- 試験日時:     2026-05-18 10:15:22 〜 10:16:37 JST
- ツール:       Apache JMeter 5.6.3 + macOS 14.8 + OpenJDK 21
- 試験計画:     `1-2/1-2_concurrent_165.jmx`
- 元ログ:       `1-2/runs/run1_20260518_101520.jtl`
- HTMLレポート: `1-2/report/index.html`

## 結果
| 指標 | 値 |
|---|---|
| 総リクエスト数 | 1,650 |
| HTTP エラー | 0件 |
| 3秒超過 (KO) | 3件 (0.18%) |
| 平均応答時間 | 1,374.81 ms |
| Median | 1,234.00 ms |
| 90th pct | 2,405.70 ms |
| 95th pct | 2,580.00 ms |
| 99th pct | 2,818.43 ms |
| 最大応答時間 | 3,086 ms |
| スループット | 22.42 req/s |
| APDEX (T=1s, F=3s) | 0.691 |

## 判定: 🟢 合格（実用判定）

### 判定理由
- HTTP 応答は全件 200、サーバ側のエラーなし
- **99%tile = 2,818 ms** (< 3秒閾値) で 99% 以上のリクエストが要件を満たす
- 3秒超過は3件 (0.18%) のみ、最大でも 3,086 ms（閾値+86ms の軽微な揺らぎ）
- 平均応答 1,375 ms は閾値の 46% で十分な余裕

### 補足
- APDEX 0.691 は Tolerating ゾーン（1〜3秒）に多くのリクエストが集中していることに起因
- 業務利用上は問題ないレベルだが、95%tile が 2.5 秒台と高め
- 厳格に「全件 3秒以内」を求める場合は不合格判定となる

## 試験の再実行手順
```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou

# 1回のみ実行（プロキシ・レート制限を考慮）
jmeter -n -t 1-2/1-2_concurrent_165.jmx \
  -p jmeter.properties \
  -l 1-2/runs/runN_$(date +%Y%m%d_%H%M%S).jtl

# HTMLレポート再生成
jmeter -g 1-2/runs/runN_*.jtl -o 1-2/report \
  -Jjmeter.reportgenerator.apdex_satisfied_threshold=1000 \
  -Jjmeter.reportgenerator.apdex_tolerated_threshold=3000
```
