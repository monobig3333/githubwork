# M-4 MID サーバ高負荷時リソース使用率確認（ローカル実行版）

| 項目 | 内容 |
|---|---|
| 対象 | MID サーバ（3 AZ 構成・各 AZ 1 台） |
| 計測ツール | `monitor_local.sh` … MID サーバ上でローカル実行する Bash |
| 負荷生成 | Zabbix（外部）30,000件/10分 |
| 計測項目 | CPU 使用率 / メモリ使用率 / Load average / MID プロセス CPU / MID スレッド数 |
| 合否基準 | CPU 80% 以下 / メモリ 90% 以下 / MID スレッド数が異常増加しないこと（参考値） |

## SSH 不要・ローカル実行

`monitor_local.sh` を **各 MID サーバに 1 度だけ転送** し、それぞれの MID サーバ上で **直接** 実行する。
リモートからの SSH 接続は不要。

## 実行手順

### 1. スクリプト配備（各 MID サーバへ）

```bash
# 例：手元から scp（手元 → MID）
scp M-4/monitor_local.sh user@mid-1:/tmp/
scp M-4/monitor_local.sh user@mid-2:/tmp/
scp M-4/monitor_local.sh user@mid-3:/tmp/
```

> scp も使えない場合は、各 MID 上で `cat > monitor_local.sh` でファイル作成し、内容をペーストする運用でも可。

### 2. Zabbix 負荷投入を別端末で起動

30,000件/10分 の高負荷を 10 分以上継続する設定で投入を開始する。

### 3. 各 MID サーバで計測スクリプトを実行（並走）

```bash
# MID Server #1 (terminal 1)
bash /tmp/monitor_local.sh 600     # 600秒 = 10分

# MID Server #2 (terminal 2)
bash /tmp/monitor_local.sh 600

# MID Server #3 (terminal 3)
bash /tmp/monitor_local.sh 600
```

実行中は CPU / メモリを 5 秒間隔でサンプリング。終了時に summary を表示する。

#### オプション

```bash
DURATION=1800 INTERVAL=5 CPU_THRESHOLD=80 MEM_THRESHOLD=90 bash /tmp/monitor_local.sh
```

### 4. 出力ファイル

各 MID サーバの実行ディレクトリに以下が生成される（スクリプトと同じ場所）:

```
M-4_<hostname>_<UTC_TS>.csv         # 時系列メトリクス
M-4_<hostname>_<UTC_TS>.summary.txt # max / avg と合否判定
```

### 5. CSV を手元に回収して集計

```bash
# 各 MID から手元へ
scp user@mid-1:/tmp/M-4_*.csv M-4/
scp user@mid-2:/tmp/M-4_*.csv M-4/
scp user@mid-3:/tmp/M-4_*.csv M-4/

# 全体集計
python3 M-4/aggregate.py M-4/M-4_*.csv

# 詳細を JSON で見たい
python3 M-4/aggregate.py --json M-4/M-4_*.csv
```

`aggregate.py` は 3 台の CSV を表形式で並べて、CPU max / MEM max が閾値を超えていれば NG を表示。

## CSV スキーマ

```
ts, host, cpu_pct, mem_used_kb, mem_total_kb, mem_pct,
load1, load5, load15, mid_pid, mid_cpu_pct, mid_rss_kb, mid_threads
```

- `cpu_pct` … システム全体の CPU 利用率（`100 - %idle`）
- `mem_pct` … `/proc/meminfo` から `(MemTotal - MemAvailable) / MemTotal * 100`
- `mid_*` … MID Server のメイン Java プロセスの CPU / 常駐メモリ / スレッド数

## 依存

`monitor_local.sh` は標準的な Linux で動作（依存: `bash`, `awk`, `top`, `ps`, `uptime`, `/proc`, `pgrep`）。
`aggregate.py` は手元の Python 3 で実行（標準ライブラリのみ）。
