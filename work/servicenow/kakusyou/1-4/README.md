# 1-4 チケット起票数（月間処理量）

| 項目 | 内容 |
|---|---|
| ツール | Playwright (ループ起票) |
| 件数 | 1000件 |
| 合否基準 | 全件成功・欠損/重複なし |

## 実行

```bash
pytest 1-4/ -v -s             # -s で進捗ログを表示
```

実行結果は `result_1_4.json` に保存される。1000件は時間がかかるため、
事前に小さい件数で動作確認することを推奨（`TICKET_COUNT` を変更）。

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```
