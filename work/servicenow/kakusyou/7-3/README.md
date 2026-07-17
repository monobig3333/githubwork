> ⚠️ **試験方式変更（重要）**
> ServiceNow 社は SaaS インスタンスの冗長化試験（顧客向けフェイルオーバー試験）を
> 実施しない方針のため、本要件は **ドキュメントレビューで代替** する。
> 詳細・判定は `RESULT.md` を参照。以下の Playwright 手順は、
> 将来フェイルオーバー試験が可能になった場合の予備として保持しているもの。

# 7-3 系切り替え後のデータ継続性

| 項目 | 内容 |
|---|---|
| ツール | Playwright + ServiceNow REST API |
| 合否基準 | 切り替え後もデータロスなく参照可能 |

## 手順

```bash
# 1) フェイルオーバー前に投入
pytest 7-3/test_7_3_failover_data.py::test_inject_before_failover -v

# 2) ServiceNow 担当者にフェイルオーバー試験を依頼

# 3) フェイルオーバー後に確認
pytest 7-3/test_7_3_failover_data.py::test_verify_after_failover -v
```

`injected_ids.json` に投入レコードIDが保存される。
SaaS制約でフェイルオーバー試験が実施できない場合は、仕様書レビューで代替（このテストはスキップ）。

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```
