# M-1 MIDサーバ イベント転送スループット（通常時）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter + MIDサーバログ |
| 負荷 | 10スレッド × 30loop（標準負荷） |
| 合否基準 | 転送完了まで3分30秒以内（SLA: 3分30秒）、転送漏れなし |

## 動作
1. JMeter から MIDサーバ経由で em_event を投入
2. MIDサーバの `agent.log` で受信時刻、ServiceNow側の `em_event.sys_created_on` で転送時刻を取得
3. 差分が3秒以内であることを確認

## 実行
```bash
jmeter -n -t M-1/M-1_mid_throughput_normal.jmx \
  -p jmeter.properties \
  -l M-1/result.jtl -e -o M-1/report/

# MIDサーバ側ログ確認（並行）
for h in $(echo $MID_HOSTS | tr ',' ' '); do
  ssh midserver@$h 'tail -f /opt/midserver/agent/logs/agent0.log.0' | tee -a logs/$h.log &
done
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
