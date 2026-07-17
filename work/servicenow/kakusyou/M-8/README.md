# M-8 停止AZの自動復旧

| 項目 | 内容 |
|---|---|
| ツール | Playwright + ServiceNow MID Server 管理画面 (ecc_agent) |
| 合否基準 | 手動介入なしで「Up」になり、イベント転送再開 |

## 手順

```bash
# 1) 対象MIDサーバを起動（手動）
ssh midserver@mid-a.example.com 'sudo systemctl start mid'

# 2) Playwright で監視
pytest M-8/ -v
```

`.env` の `MID_HOSTS` の先頭サーバが対象。10分間ポーリングして
ecc_agent のステータスが「Up」になることを確認する。

## SSO 認証

`auth.json` （Google SSO で取得した storage_state）が必要。未取得なら:

```bash
python3 _common/save_auth_state.py
```
