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


---

## 再測定 2026/8/19 (biglobedev)

### 判定: **OK**

### 試験条件

- 同時接続: 165 スレッド / ランプアップ 60 秒 / 10 ループ（総 1,650 リクエスト）
- API: `GET /api/now/table/incident?sysparm_limit=20`
- コマンド: `-Jthreads=165 -Jramp_up=60 -Jloop.count=10`

### 結果

| 指標 | 実測 |
|---|---|
| 総リクエスト数 | 1,651 |
| レスポンスコード | 200 × 1,651 |
| **失敗** | **0 件** |
| 平均応答時間 | 316 ms |
| 中央値 | 281 ms |
| 90 パーセンタイル | 479 ms |
| 95 パーセンタイル | 591 ms |
| 99 パーセンタイル | 753 ms |
| 最大応答時間 | 2,474 ms |
| **3 秒超過** | **0 件** |
| 実行時間 | 78 秒 |
| スループット | 21.1 req/s |

### 判定理由

- 165 クライアント同時接続で **HTTP エラー 0 件**、接続拒否・タイムアウトなし
- **全 1,650 リクエストが 3 秒以内**（最大 2,474 ms、99%tile 753 ms）
- 前回（2026/5/18・同 dev）は 3 秒超過 3 件・平均 1,375 ms の「実用判定」での合格だったが、
  今回は厳格な「全件 3 秒以内」を満たしており、明確に改善している


### 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/08/19 |
| 実施時刻 | 13:48:08 〜 13:49:26 |
| 対象インスタンス | biglobedev (Zurich) |
| 認証方式 | OAuth Client Credentials (Bearer Token) |
| ツール | Apache JMeter 5.6.3 |
| 元ログ | `1-2/runs/run_20260819_134803.jtl` |

> dev の MID Server は 1 台構成 (t3.large / ヒープ 4096 MB)。Excel の前提条件
> 「3AZ 全ての MID サーバが稼働中」は満たしていない。
