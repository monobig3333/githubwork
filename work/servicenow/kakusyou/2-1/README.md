# 2-1 アラームビューワー同時接続（165クライアント）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter |
| スレッド | 165 / ランプアップ60秒 |
| 合否基準 | エラー0件、画面が正常に描画される |

## 実行
```bash
jmeter -n -t 2-1/2-1_alarm_viewer_165.jmx \
  -q jmeter.properties \
  -l 2-1/result.jtl -e -o 2-1/report/
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
