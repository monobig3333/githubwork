# N-2 異常状態下の動作継続：CPU 100% 状態

| 項目 | 内容 |
|---|---|
| 異常条件 | 他プロセスが CPU を 100% に張り付かせる |
| 期待動作 | MID Server がイベント転送を継続 |
| 対象 MID | stg-1 |
| 計測時間 | 既定 600 秒 |
| 合否基準 | em_event 到達の最大ギャップが 60 秒以内 |

## 実行 (3 端末)

### 端末 A (手元)
```bash
python3 N-common/verify_continuity.py \
    --label N-2 --duration 600 --max-gap 60 \
    --output N-2/result.json
```

### 端末 B (MID Server stg-1)
```bash
bash /tmp/stress_cpu.sh 600
# vCPU 数の半分でやりたい場合
CPUS=2 bash /tmp/stress_cpu.sh 600
```

### 端末 C
Zabbix 投入を継続。

両端末で負荷が立ち上がってから 手元で Enter。

## 出力
`N-2/result.json`

## 補足
`awk 'BEGIN{while(1) {x++}}'` で CPU を回し続ける。`stress-ng` 等の追加ツールは不要。
