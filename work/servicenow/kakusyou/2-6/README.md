# 2-6 イベント描画応答時間（高負荷継続30分）

| 項目 | 内容 |
|---|---|
| 対象 ServiceNow | biglobenonprod（Zurich） |
| 対象画面 / テーブル | イベントビューワー `em_event_list.do` / `em_event` |
| 計測ツール | Playwright（DOM 描画検知）+ ServiceNow Table API |
| 負荷生成 | **Zabbix（外部）** … 別端末から手動起動 |
| 計測継続時間 | 既定 1800 秒 = 30 分（`PERF_DURATION_SEC` で上書き可） |
| 計測件数上限 | 既定 150 件（`PERF_MAX_ITER` で上書き可） |
| 合否基準 | 平均 60 秒以内 / 最大 180 秒以内 / 性能飽和なし |

## 性能飽和の判定

サンプルを前半 15 分・後半 15 分に分け、それぞれの平均応答時間を比較。
- 後半平均 / 前半平均 ＞ **1.5** → 飽和とみなし NG
- 1.5 倍以内 → 飽和なし（OK）

## 動作概要

1. テストプログラムが `auth.json` で SSO 済セッションを使い、イベントビューワー (`em_event_list.do`) を開く
2. プログラムが **Enter 入力を待ち合わせ**
3. 別端末で Zabbix の高負荷継続投入（30 分間）を起動
4. ServiceNow にイベントが流れ始めたら Enter を押す
5. テスト側で `em_event` を `sys_created_on>計測開始時刻` で **降順** ポーリング（cookie + X-UserToken 認証）
6. 計測済み sys_id は除外しつつ、新規イベントの `sys_created_on (UTC)` → ビューワー DOM 描画完了 までの経過時間を継続計測
7. 経過時間 `DURATION_SEC` または計測件数 `MAX_ITERATIONS` 到達で終了
8. 前半 15 分／後半 15 分の比較で飽和判定

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

# 既定 (1800s, 150件) で実行
pytest 2-6/ -v -s

# 短縮 (例: 10 分 / 60 件) でドライラン
PERF_DURATION_SEC=600 PERF_MAX_ITER=60 pytest 2-6/ -v -s
```

`-s` は `input()` プロンプト表示のため必須。

### 端末 B（負荷投入用）

`Enter で計測開始 >` プロンプトが出る前に Zabbix を 30 分継続投入できる設定でスタンバイ → スクリプト起動 → プロンプトで Enter。

## 出力

- `result_2_6.json` … 統計（overall / first_half / second_half + saturated 判定）＋ 各 iteration の生データ（rel_t_sec を含む時系列）
- `pytest report.html` … トップディレクトリ

## 補足

- 既存の旧 JMX (`2-6_alarm_sustained_30min.jmx`) は使用しない方針（Zabbix 外部投入に統合）。
- 30 分継続で 150 件取れれば 1 件あたり平均 12 秒に 1 回ペースで計測可能。
