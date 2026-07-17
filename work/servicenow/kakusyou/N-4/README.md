# N-4 異常状態下の動作継続：Disk Full

| 項目 | 内容 |
|---|---|
| 異常条件 | 該当 FS の残空きを **0 (100% 使用率)** まで埋める |
| 期待動作 | MID Server がイベント転送を継続 |
| 対象 MID | stg-1 |
| 計測時間 | 既定 600 秒 |
| 合否基準 | em_event 到達の最大ギャップが 60 秒以内 |

## 実行 (3 端末)

### 端末 A (手元)
```bash
python3 N-common/verify_continuity.py \
    --label N-4 --duration 600 --max-gap 60 \
    --output N-4/result.json
```

### 端末 B (MID Server stg-1)
```bash
# 既定: /tmp を 100% 使用率まで埋める
bash /tmp/stress_disk_full.sh 600

# 別 FS を埋めたい場合
TARGET=/var/tmp/n4.bin bash /tmp/stress_disk_full.sh 600

# 100% ではなく N MB だけ残したい場合
LEAVE_FREE_MB=50 bash /tmp/stress_disk_full.sh 600
```

#### 充填の仕組み

1. **Phase 1 (一次充填)**: `fallocate` (失敗時 dd) で空きの大部分を一気に埋める
2. **Phase 2 (top-up)**: 残空きが LEAVE_FREE_MB を超えていれば、1 MB ずつ追記して **ENOSPC まで詰める**

### 端末 C
Zabbix 投入を継続。

## 出力
`N-4/result.json`

## ⚠️ 安全に関する注意

- 既定の **100% 使用率** では以下が書き込み不能になる可能性:
  - syslog / journald
  - MID Server の `/opt/midserver/agent/logs/*.log` (同 FS 上の場合)
  - sshd の audit / セッションログ
- システムが完全に詰まると応答が遅くなることがある
- スクリプトは終了時に必ず `rm -f $TARGET` を実行する。
  万一 kill -9 された場合は手動で削除:

```bash
rm -f /tmp/n4_diskfull.bin
sync
```

- MID Server のログ FS とは異なる場所を埋めたい場合は `TARGET` を別ボリュームに設定する
