# N-3 異常状態下の動作継続：メモリ不足

| 項目 | 内容 |
|---|---|
| 異常条件 | 他プロセスがメモリを大量確保し空きを圧迫 |
| 期待動作 | MID Server がイベント転送を継続。MID 自体は OOM Killer の対象にしない |
| 対象 MID | stg-1 |
| 計測時間 | 既定 600 秒 |
| 合否基準 | em_event 到達の最大ギャップが 60 秒以内 |

## メモリ配分の考え方

MID Server の **Java Max ヒープ (既定 4096 MB)** ＋ **OS バッファ (既定 512 MB)** を確保したうえで、残りを Python で圧迫する設計。

```
MB = MemTotal - MID_MAX_MB(4096) - OS_BUFFER_MB(512)
```

例: 8GB システムなら 8192 - 4096 - 512 = **3584 MB** を圧迫。これで「メモリ不足だが MID は OOM されない」状態を作る。

## 実行 (3 端末)

### 端末 A (手元)
```bash
python3 N-common/verify_continuity.py \
    --label N-3 --duration 600 --max-gap 60 \
    --output N-3/result.json
```

### 端末 B (MID Server stg-1)
```bash
# 既定 (MemTotal - 4096 - 512 を圧迫)
bash /tmp/stress_memory.sh 600

# Java ヒープが違うサイズの場合は調整
MID_MAX_MB=2048 bash /tmp/stress_memory.sh 600

# 直接 MB 指定 (最優先)
MB=2048 bash /tmp/stress_memory.sh 600

# 旧モード: 全体の % で指定 (MID 残量を考慮しないので注意)
PCT=70 bash /tmp/stress_memory.sh 600
```

### 端末 C
Zabbix 投入を継続。

## 出力
`N-3/result.json`

## 補足

- 本スクリプトは `oom_score_adj` を 1000 にセットして、OOM Killer に **自分自身が先に殺されるよう** にしている。MID Server (java) を巻き添えにしないための保険。
- 旧版（PCT=80 既定）では MID Java のヒープ確保まで奪い、GC が長引き em_event 到達が止まるケースが発生した。本版では Java Max ヒープを必ず残す。
- `swap` が大きく設定されていると、メモリ不足状態にならずに swap 退避するだけになる場合がある。`free -h` で確認。
