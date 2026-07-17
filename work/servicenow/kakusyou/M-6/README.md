# M-6 2AZ停止時のイベント転送継続

| 項目 | 内容 |
|---|---|
| ツール | JMeter + Playwright + 手動停止 |
| 合否基準 | 2AZ停止中も残り1AZで継続、サービス断なし |

## 実行
```bash
jmeter -n -t M-6/M-6_event_during_2az_down.jmx -p jmeter.properties -l M-6/load.jtl &
ssh midserver@mid-a.example.com 'sudo systemctl stop mid'
ssh midserver@mid-b.example.com 'sudo systemctl stop mid'
pytest M-6/ -v
```

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
