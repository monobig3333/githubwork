# 3-1 ワークフロー並列実行（100プロセス）

| 項目 | 内容 |
|---|---|
| ツール | Apache JMeter (REST API) |
| リクエスト | `POST /api/now/table/incident` |
| 並列数 | 100スレッド／同時起動（loop 1 = 100 起票） |
| 合否基準 | 100プロセス並列実行、干渉・エラーなし |
| 許容レスポンス | 200 または 201 / 応答 3 秒以内 |

## 起動方式

Workflow を直接叩く専用 API ではなく、**インシデントを並列起票して、それを契機に
走るワークフロー／フローの並列実行を確認する**方式。リクエストボディは次のとおり。

```json
{
  "short_description": "[3-1] perf test parallel workflow ${__threadNum}-${INC_NO}-${__time(,)}",
  "category": "inquiry",
  "description": "Automated test from JMeter for requirement 3-1 (Workflow Parallel Execution)"
}
```

> 旧 README には トリガ URL `/api/sn_ind_pmpf/workflow/trigger` を「サンプル」とする記載が
> あったが、JMX は既に incident 起票方式に差し替わっている（2026/7/31 確認）。

## ⚠️ 書き込みを伴う試験

**本試験は対象インスタンスに実際にインシデントを作成する。** スレッド数 × ループ数だけ
レコードが増えるため、動作確認時はスレッド数を絞ること。

作成されたレコードは `short_description` が `[3-1] perf test parallel workflow` で始まる。
確認・後片付けは次で行う。

```bash
CID=$(grep '^snow.client_id=' jmeter.properties | cut -d= -f2-)
SEC=$(grep '^snow.client_secret=' jmeter.properties | cut -d= -f2-)
TOKEN=$(curl -s -u "$CID:$SEC" -d 'grant_type=client_credentials' \
  https://biglobenonprod.service-now.com/oauth_token.do | jq -r .access_token)

# 件数確認
curl -s -H "Authorization: Bearer $TOKEN" \
  'https://biglobenonprod.service-now.com/api/now/table/incident?sysparm_query=short_descriptionSTARTSWITH%5B3-1%5D%20perf%20test&sysparm_fields=number,sys_id,sys_created_on&sysparm_limit=200' \
  | jq '.result | length'
```

## 実行

```bash
# 動作確認（3 件だけ起票）
jmeter -n -t 3-1/3-1_workflow_parallel.jmx -q jmeter.properties \
  -Jthreads=3 -Jramp_up=1 -Jloop.count=1 -Jthroughput=60 \
  -l 3-1/runs/smoke_$(date +%Y%m%d_%H%M%S).jtl

# 本番（100 並列同時起動）
jmeter -n -t 3-1/3-1_workflow_parallel.jmx -q jmeter.properties \
  -Jthreads=100 -Jramp_up=10 -Jloop.count=1 \
  -l 3-1/result.jtl -e -o 3-1/report/
```

## OAuth 認証

`jmeter.properties` に `snow.client_id` / `snow.client_secret` を設定。
JMX 内の setUp Thread Group が `/oauth_token.do` で client_credentials grant
を実行し、取得した access_token を全リクエストの Bearer ヘッダに自動セットする。
