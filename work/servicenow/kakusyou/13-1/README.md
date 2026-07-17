# 13-1 拡張性確認（ユーザ数・データ量2倍）

| 項目 | 内容 |
|---|---|
| ツール | JMeter（330スレッド）+ Playwright |
| 合否基準 | 性能要件を維持、データ量2倍でも劣化が許容範囲内 |

## 前提
- 事前に `1-1/` で baseline 計測済みであること（`result_1_1.json` が存在）
- データ量2倍のテストデータ準備済み

## 実行
```bash
# JMeter（2倍負荷）
jmeter -n -t 13-1/13-1_scalability_2x.jmx -p jmeter.properties -l 13-1/load.jtl

# Playwright で画面応答時間を計測
pytest 13-1/ -v
```

baseline との差分（劣化率）が `result_13_1.json` に記録される。

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
