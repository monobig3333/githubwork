# 1-3 同時接続330クライアント（参照専用）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter |
| スレッド | 330 |
| ランプアップ | 120秒 |
| 合否基準 | エラー0件、接続拒否/タイムアウトなし |

## 実行
```bash
jmeter -n -t 1-3/1-3_concurrent_330_readonly.jmx \
  -p jmeter.properties \
  -l 1-3/result.jtl -e -o 1-3/report/
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
