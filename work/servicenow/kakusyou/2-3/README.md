# 2-3 イベント描画応答時間（通常時）

| 項目 | 内容 |
|---|---|
| 対象 ServiceNow | biglobenonprod（Zurich） |
| 対象画面 / テーブル | イベントビューワー `em_event_list.do` / `em_event` |
| 計測ツール | Playwright（DOM 描画検知）+ ServiceNow Table API |
| 負荷生成 | **Zabbix（外部）** … 別端末から手動起動 |
| 計測回数 | 20 回 |
| 合否基準 | 受信 → 描画完了 まで 3 秒以内 |

## 動作概要

1. テストプログラムが `auth.json` で SSO 済セッションを使い、イベントビューワー (`em_event_list.do`) を開く
2. プログラムが **Enter 入力を待ち合わせ**
3. 別端末で Zabbix の負荷投入スクリプトを起動
4. ServiceNow にイベントが流れ始めたら Enter を押す
5. テスト側で `em_event` を `sys_created_on>計測開始時刻` で昇順ポーリング
   - 認証は `auth.json` の cookie + `X-UserToken`（`window.g_ck`）
   - OAuth / AWS は不要
6. 新規イベントが届く度に、`sys_created_on (UTC)` → ビューワー DOM への描画完了時刻 までの経過時間を計測（20 件）
7. 最大値が 3 秒未満であれば合格

## 前提

- `.env` に以下を設定済み
  - `SNOW_INSTANCE=biglobenonprod`
  - `SNOW_BASE_URL=https://biglobenonprod.service-now.com`
- `auth.json` を最新化（期限切れの場合）
  ```bash
  python3 _common/save_auth_state.py            # bundled Chromium (推奨)
  # または
  python3 _common/save_auth_state.py --chrome   # インストール済み Chrome
  ```
- 実行端末・ServiceNow とも **NTP 同期** されていること（時計ずれが直接誤差になる）

## 実行手順

### 端末 A（計測用）

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
pytest 2-3/ -v -s
```

`-s` は `input()` プロンプト表示のため必須。

### 端末 B（負荷投入用）

`Enter で計測開始 >` のプロンプトが出る前に、別端末で Zabbix 負荷投入をスタンバイ → スクリプト起動 → プロンプトで Enter を押す。

## 出力

- `result_2_3.json` … 統計（min/avg/max/p95）＋ 各 iteration の生データ（event_number / sys_id / message_key / source / node / resource / type / severity / sys_created_on_utc / rendered_epoch / elapsed_sec）
- `pytest report.html` … トップディレクトリ

## 認証メモ

ServiceNow REST API は cookie だけでは 401 を返す（CSRF 対策）。
ブラウザの `window.g_ck` を読み取り `X-UserToken` ヘッダで送ることで、`auth.json` 経由のセッションだけで API を叩ける。診断スクリプトは `2-3/api_probe.py` を参照。

## トラブルシュート

| 症状 | 原因 / 対処 |
|---|---|
| 新規イベントが届かない | Zabbix → MID → em_event の経路を確認（MID Server の状態、Connector 設定など） |
| max が 3 秒を超える | viewer のリロード負荷で見かけ上悪化することがあるため、計測条件を要件チームと再合意 |
| 認証エラー(401) | `auth.json` 期限切れ → `save_auth_state.py` を再実行 |
| 時間がマイナス | クライアント vs ServiceNow の NTP ズレ → 両端の時刻同期を確認 |
