# 7-1 24時間365日 稼働確認（SLA） — 確証

## 要件
- 稼働率 99.8% 以上が SLA で保証されていること
- Trust Site の実績値が 99.8% 以上であること
- 試験方式: ドキュメントレビュー

## 確証1: SLA 99.8% 保証（契約ドキュメント）

ServiceNow の **Availability SLA** は、本番インスタンス（production instances）が
**暦月あたり 99.8% 以上** 利用可能であることを保証している（Excused Downtime を除く）。

| 項目 | 内容 |
|---|---|
| 保証稼働率 | **99.8% / 暦月**（production instances） |
| 算定単位 | カレンダー月ごと |
| 除外 | Excused Downtime（計画メンテナンス等） |
| 冗長性 | 電源・冷却・ネットワーク・セキュリティ・サーバを含むフルスタックの冗長化・耐障害設計 |
| SLA 未達時の救済 | サブスクリプション期間の延長、またはサービスクレジット発行 |

### エビデンス取得元（公式・要保存）
- **Subscription Service Agreement**（ServiceNow 公式法務ドキュメント, PDF）
  https://www.servicenow.com/content/dam/servicenow-assets/public/en-us/doc-type/legal/servicenow-subscription-service-agreement.pdf
- **Subscription Service Guide**（同上）
  https://www.servicenow.com/content/dam/servicenow-assets/public/en-us/doc-type/legal/subscription-service-guide-upgrade.pdf

→ この2つの PDF を取得し、「Availability SLA」「99.8%」の記述ページを
　 エビデンスとして 7-1 ディレクトリに保存すること。

## 確証2: Trust Site / 稼働実績

| サイト | URL | 用途 |
|---|---|---|
| ServiceNow Trust（TrustShare） | https://trust.servicenow.com/ | セキュリティ・コンプライアンス・信頼性情報 |
| Data Center Status | https://status.service-now.com/ | データセンター稼働状況・インシデント履歴 |

> ⚠️ 試験計画書には「status.servicenow.com」とあるが、正しいデータセンター
> ステータスページは **`status.service-now.com`**（ハイフン入り）。

### 実施事項（エビデンス収集）
1. `status.service-now.com` で biglobeprod / biglobenonprod が所属する
   データセンターの稼働実績を確認
2. 過去12ヶ月分の計画外停止（unplanned outage）履歴を取得
3. 稼働率を算出し 99.8% 以上であることを確認
4. 画面キャプチャを 7-1 ディレクトリに保存

## 判定: 🟢 合格（2026-05-21 完了）

| 観点 | 状態 | 判定 |
|---|---|---|
| SLA で 99.8% 保証 | ServiceNow 公式契約で **99.8% 保証を確認** | 🟢 合格 |
| Trust Site 実績 99.8%+ | status.service-now.com で対象DCの稼働実績を確認 | 🟢 合格 |

担当: 小野 / 実施日: 2026-05-21 / 結果: OK

SLA 契約で 99.8% が保証されており、Trust Site の稼働実績も基準を満たすことを
ドキュメントレビューで確認した。

## 実施記録
- [x] Subscription Service Agreement で 99.8% SLA 保証を確認
- [x] status.service-now.com で対象 DC の稼働実績を確認
- [x] 稼働率が 99.8% 以上であることを確認
- 実施日: 2026-05-21 / 担当: 小野

## 備考
- 99.8% / 月 = 約 87.7 分/月 までのダウンタイムが許容範囲。
- ServiceNow は SaaS インスタンスの冗長化試験を顧客向けに実施しないため
  （7-2/7-3/7-4 参照）、本要件もドキュメント・実績値レビューで評価する。
