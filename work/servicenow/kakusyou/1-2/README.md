# 1-2 同時接続165クライアント（参照/更新）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter |
| スレッド | 165 |
| ランプアップ | 60秒 |
| ループ | 10回 |
| 合否基準 | エラー0件、応答時間 3秒以内 |

## 実行

```bash
jmeter -n -t 1-2/1-2_concurrent_165.jmx \
  -p jmeter.properties \
  -l 1-2/result.jtl \
  -e -o 1-2/report/
```

`jmeter.properties` で snow.host / snow.user / snow.password を設定。

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
