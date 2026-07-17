# M-5 1AZ停止時のイベント転送継続

| 項目 | 内容 |
|---|---|
| ツール | JMeter + Playwright + 手動停止 |
| 期間 | 5分 |
| 合否基準 | 1AZ停止中も残り2AZで転送継続、描画継続、サービス断なし |

## 実行手順

```bash
# T1: JMeterで継続投入
jmeter -n -t M-5/M-5_event_during_1az_down.jmx -p jmeter.properties -l M-5/load.jtl

# T2: 1AZのMIDサーバを停止（タイミングを見計らって）
ssh midserver@mid-a.example.com 'sudo systemctl stop mid'

# T3: Playwright でアラームビューワー継続性を監視
pytest M-5/ -v
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
