# N-1 異常状態下の動作継続：Disk I/O 高負荷

| 項目 | 内容 |
|---|---|
| 異常条件 | 他プロセスが Disk I/O を継続消費 |
| 期待動作 | MID Server がイベント転送を継続（Zabbix → ServiceNow 到達が途切れない） |
| 対象 MID | stg-1 (1 台で証跡取得) |
| 計測時間 | 既定 600 秒 |
| 合否基準 | 計測区間中、em_event 到達の最大ギャップが 60 秒以内 |

## 実行手順 (3 端末)

### 端末 A (手元) — 検証スクリプト

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
python3 N-common/verify_continuity.py \
    --label N-1 --duration 600 --max-gap 60 \
    --output N-1/result.json
```

`Enter で計測開始 >` で待機。

### 端末 B (MID Server stg-1) — 負荷生成

```bash
# 事前に scp などで N-1/stress_disk_io.sh を MID へ配置
bash /tmp/stress_disk_io.sh 600
```

### 端末 C (Zabbix 投入) — 既存の Zabbix 高負荷投入を回す（または通常監視のまま）

### 手元で Enter

両端末が動き始めたら、手元ターミナルで Enter を押す。

## 出力

- `N-1/result.json` … イベント到達タイムライン + 最大ギャップ + 判定

## チューニング

```bash
PARALLEL=4 BLOCK_MB=1024 bash /tmp/stress_disk_io.sh 600
```

## クリーンアップ

スクリプトは終了時に `/tmp/n1_diskio_*.bin` を削除し、子プロセスを終了する。
強制終了 (kill -9) された場合は手動削除:

```bash
rm -f /tmp/n1_diskio_*.bin
```
