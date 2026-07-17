# M-7 AZ停止中のデータロスなし確認

| 項目 | 内容 |
|---|---|
| ツール | Python（ログ突合）+ ServiceNow Table API |
| 合否基準 | 欠損ゼロ、重複ゼロ |

## 入力
- 送信側CSV（JMeterの ResponseAssertion を通過した message_key 列）
- ServiceNow `em_event.source` の値

## 実行
```bash
# JMeter 実行時に -Jjmeter.save.saveservice.requestHeaders=true を付与し、
# あるいは BeanShell PostProcessor で message_key を sent_keys.csv に書き出しておく
python3 M-7/check_m_7_data_loss.py \
  --sent-csv M-5/sent_keys.csv \
  --source mid-test-M-5
```

突合結果は `result_m_7.json`。

## 認証

`_common/snow_client.py` 経由でServiceNow REST APIにアクセスする。
OAuth Client Credentials の認証情報は `.env` の SNOW_CLIENT_ID/SNOW_CLIENT_SECRET、
または AWS Secrets Manager（SNOW_SECRET_NAME）から自動取得される。
