# M-9 全AZ停止時の挙動・復旧後再送

| 項目 | 内容 |
|---|---|
| ツール | Python（手動停止・起動とログ確認） |
| 合否基準 | 復旧後にキューイングされたイベントが漏れなく転送される、または全AZ停止時にアラート発報 |

## 手順

```bash
# 1) 3AZ全MIDサーバを停止
for h in $(echo $MID_HOSTS | tr ',' ' '); do
  ssh midserver@$h 'sudo systemctl stop mid'
done

# 2) 全停止中にイベントを100件投入（投入失敗が想定される）
python3 M-9/check_m_9_queue_and_redelivery.py --inject-only --injection-count 100

# 3) ServiceNow管理コンソールで MIDサーバ Down アラートが上がっているか確認

# 4) 3AZ全MIDサーバを起動
for h in $(echo $MID_HOSTS | tr ',' ' '); do
  ssh midserver@$h 'sudo systemctl start mid'
done

# 5) 数分待ってから受信確認
python3 M-9/check_m_9_queue_and_redelivery.py --verify-only
```

`sent_keys.txt` に投入キー、`result_m_9.json` に突合結果。

## 認証

`_common/snow_client.py` 経由でServiceNow REST APIにアクセスする。
OAuth Client Credentials の認証情報は `.env` の SNOW_CLIENT_ID/SNOW_CLIENT_SECRET、
または AWS Secrets Manager（SNOW_SECRET_NAME）から自動取得される。
