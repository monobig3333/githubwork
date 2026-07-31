# M-2 MIDサーバ転送スループット（最大負荷 30,000件/10分）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter |
| 投入 | 30,000件 / 10分（=3000/分）×3AZ MID Server経由 |
| 合否基準 | 全イベント転送、処理漏れ/スキップなし |

## 実行
```bash
jmeter -n -t M-2/M-2_mid_throughput_max.jmx \
  -q jmeter.properties \
  -l M-2/result.jtl -e -o M-2/report/
```

## 投入数と転送数の突合
```bash
# JMeter 送信成功数
grep -c ',true,' M-2/result.jtl

# ServiceNow 側受信数
curl -u "$USER:$PASS" \
  "https://$HOST/api/now/table/em_event?sysparm_query=source=mid-test-M-2&sysparm_count=true"
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
