# N-5 異常検出：TCP セッション枯渇 - 試験結果

## 判定: **OK**

| 指標 | 値 | 合否基準 | 判定 |
|---|---|---|---|
| 計測期間 | 900 秒 (15 分) | — | — |
| 観測した status | `Up`, `Down` | — | — |
| **異常検出** | **True** | 1 回以上 status が Up 以外 | ✅ |
| 初回異常検出時刻 (UTC) | 2026-06-05 06:46:14 | — | — |
| 検出までの経過時間 | 約 8 分 33 秒 | — | — |
| API エラー数 | 0 | 0 | ✅ |

## タイムライン

```
06:37:41 Z   テスト開始 / sysctl 縮小開始 → MID は Up のまま
06:46:14 Z   MID が ServiceNow 上で Down に遷移 ← 異常検出！
06:52:42 Z   テスト終了 / sysctl 自動復元
```

## 評価

- **sysctl で OS グローバルの ip_local_port_range を 32768-32800 (33 ポート) に縮小**
- 残った 33 ポートを stress_tcp.sh が握って占有
- MID Server から ServiceNow への新規 outbound 接続が事実上不可能になる
- 既存接続のハートビートが切れて再接続を試みると失敗
- 約 8 分 33 秒後に ServiceNow が **MID を Down 判定** → 期待通りの異常検出

## 実施情報

| 項目 | 内容 |
|---|---|
| 実施日 | 2026/6/5 |
| 担当 | 小野 |
| 対象インスタンス | biglobenonprod |
| 負荷対象 MID | stg-1 (mid-server-aws-zabbix-stg-1) |
| 負荷スクリプト | `N-5/stress_tcp.sh` (sysctl ip_local_port_range 縮小 + ポート奪取) |
| 検証スクリプト | `N-common/verify_mid_status.py` |
| 計測開始 (UTC) | 2026-06-05 06:37:41 |
| 計測終了 (UTC) | 2026-06-05 06:52:42 |
| 認証 | auth.json (Google SSO) + X-UserToken |

## 設計メモ

旧 ulimit ベース方式では、systemd で起動した MID daemon の fd 上限に効かず、また Zabbix 既存接続のポートを奪い続けるのが難しかった。
**sysctl で OS グローバル ephemeral port pool を縮小する方式** に切り替えたことで、確実に MID daemon にも効き、約 8 分という現実的な時間で Down を検出できた。

## 証跡

- 生データ: `result_mid_status.json` (status の時系列 436 サンプル)
- スクリプト: `stress_tcp.sh` (MID stg-1 上で実行)

## 補足

ServiceNow の MID Down 判定は heartbeat タイムアウトに依存。今回の **8 分 33 秒** という時間は、ServiceNow の `mid.heartbeat.timeout` プロパティの既定値 (約 8 分) に整合する。
