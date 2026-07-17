# 2-4/5 イベント描画応答時間（高負荷時）

| 項目 | 内容 |
|---|---|
| 対象 ServiceNow | biglobenonprod（Zurich） |
| 対象画面 / テーブル | イベントビューワー `em_event_list.do` / `em_event` |
| 計測ツール | Playwright（DOM 描画検知）+ ServiceNow Table API |
| 負荷生成 | **Zabbix（外部）** … 別端末から手動起動（30,000件/10分） |
| 計測継続時間 | 既定 600 秒（`PERF_DURATION_SEC` で上書き可） |
| 計測件数上限 | 既定 50 件（`PERF_MAX_ITER` で上書き可） |
| 合否基準 | 平均 60 秒以内 / 最大 180 秒以内 |

## 動作概要

1. テストプログラムが `auth.json` で SSO 済セッションを使い、イベントビューワー (`em_event_list.do`) を開く
2. プログラムが **Enter 入力を待ち合わせ**
3. 別端末で Zabbix の高負荷投入スクリプトを起動（30,000件/10分）
4. ServiceNow にイベントが流れ始めたら Enter を押す
5. テスト側で `em_event` を `sys_created_on>計測開始時刻` で昇順ポーリング（cookie + X-UserToken 認証）
6. 新規イベントが届く度に、`sys_created_on (UTC)` → ビューワー DOM 描画完了時刻 までの経過時間を計測
7. 経過時間 `DURATION_SEC` または計測件数 `MAX_ITERATIONS` 到達で終了
8. 平均 ≤ 60 秒 かつ 最大 ≤ 180 秒 で合格

## 前提

- `.env` に以下を設定済み
  - `SNOW_INSTANCE=biglobenonprod`
  - `SNOW_BASE_URL=https://biglobenonprod.service-now.com`
- `auth.json` を最新化（期限切れの場合）
  ```bash
  python3 _common/save_auth_state.py
  ```
- 実行端末・ServiceNow とも NTP 同期されていること

## 実行手順

### 端末 A（計測用）

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou

# 既定 (600s, 50件) で実行
pytest 2-4-5/ -v -s

# 短縮 (例: 5 分 / 30 件) でドライラン
PERF_DURATION_SEC=300 PERF_MAX_ITER=30 pytest 2-4-5/ -v -s
```

`-s` は `input()` プロンプト表示のため必須。

### 端末 B（負荷投入用）

`Enter で計測開始 >` のプロンプトが出る前に、別端末で Zabbix 負荷投入を準備 → スクリプト起動 → プロンプトで Enter を押す。

## 出力

- `result_2_4_5.json` … 統計（min/avg/max/median/p95）＋ 各 iteration の生データ
- `pytest report.html` … トップディレクトリ

## 補足

- 高負荷時はリロード自体が重くなりがちです。`RENDER_WAIT_TIMEOUT_MS` は 240 秒に拡張済み。
- 投入は 50 件/秒 (= 30,000件/10分) を想定。Zabbix 側で投入レートが極端に低い場合は計測サンプル数が不足する可能性あり。
- 既存の旧 JMX (`2-4-5_alarm_high_load.jmx`) は使用しない方針（Zabbix 外部投入に統合）。
