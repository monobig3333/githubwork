# 4-1 構成情報データ件数 上限確認（100万件）

| 項目 | 内容 |
|---|---|
| ツール | ServiceNow Import Set API + Python |
| 件数 | 1,000,000件（5万件 × 20回） |
| 合否基準 | 全件登録、登録後の検索応答時間 < 3秒 |

## 前提
- Import Set テーブル `u_perf_cmdb_load` と Transform Map `perf_cmdb_load_to_cmdb_ci` を ServiceNow 側で事前作成しておく
- Transform Map で `name`, `u_resource_id`, `asset_tag` を `cmdb_ci_server` の対応列にマップ

## 実行
```bash
# 100万件を5万件×20チャンクで投入
python3 4-1/load_4_1_cmdb_million.py

# 件数を絞ってテスト
python3 4-1/load_4_1_cmdb_million.py --total 10000 --chunk 5000

# ファイル生成だけ（投入なし）
python3 4-1/load_4_1_cmdb_million.py --skip-load
```

結果は `result_4_1.json` に保存される。

## 認証

`_common/snow_client.py` 経由でServiceNow Import Set API にアクセスする。
OAuth Client Credentials の認証情報は `.env` の SNOW_CLIENT_ID/SNOW_CLIENT_SECRET、
または AWS Secrets Manager（SNOW_SECRET_NAME）から自動取得される。
