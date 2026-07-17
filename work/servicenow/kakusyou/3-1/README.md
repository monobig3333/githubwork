# 3-1 ワークフロー並列実行（100プロセス）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter (REST API) |
| 並列数 | 100スレッド／同時起動 |
| 合否基準 | 100プロセス並列実行、干渉・エラーなし |

## 実行
```bash
jmeter -n -t 3-1/3-1_workflow_parallel.jmx \
  -p jmeter.properties \
  -l 3-1/result.jtl -e -o 3-1/report/
```

**Note**: トリガURL `/api/sn_ind_pmpf/workflow/trigger` はサンプル。
実環境では「Workflow を起動する Scripted REST API」「Flow Designer の REST trigger」等、
組織の構成に合わせて HTTPSampler.path を書き換える。

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
