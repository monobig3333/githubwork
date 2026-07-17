# 1-1 画面応答時間（通常操作）

| 項目 | 内容 |
|---|---|
| ツール | Playwright (Python / pytest) |
| 計測対象 | インシデント一覧 / インシデント詳細 / 変更チケット登録 |
| 試行回数 | 10回 / 画面 |
| 合否基準 | 平均応答時間 < 3秒 |

## 実行

```bash
pytest 1-1/ -v --headed       # 画面を見ながら実行
pytest 1-1/ -v                # ヘッドレスで実行
```

実行結果は `result_1_1.json` に保存される。

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```
