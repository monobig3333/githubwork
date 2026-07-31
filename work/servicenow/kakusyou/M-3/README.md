# M-3 MID高負荷継続時の性能飽和確認（30分継続）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter（30分継続）+ ログ分析 |
| 負荷 | 3000/分 を 30分 = 90000件 |
| 合否基準 | 転送遅延が増加し続けないこと（性能飽和なし） |

## 実行
```bash
jmeter -n -t M-3/M-3_mid_sustained_load.jmx \
  -q jmeter.properties \
  -l M-3/result.jtl -e -o M-3/report/
```

## 性能劣化の確認（時系列分析）
```bash
# 30分間を6つの5分窓に分割して平均応答時間の推移を見る
python3 - <<'PY'
import pandas as pd
df = pd.read_csv('M-3/result.jtl')
df['t'] = pd.to_datetime(df['timeStamp'], unit='ms')
df.set_index('t', inplace=True)
print(df['elapsed'].resample('5min').agg(['mean','max','count']))
PY
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
