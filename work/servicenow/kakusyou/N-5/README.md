# N-5 異常検出：TCP セッション枯渇（sysctl 縮小方式）

| 項目 | 内容 |
|---|---|
| 異常条件 | `ip_local_port_range` を一時的に 30 ポート程度まで縮小し、システム全体で新規 outbound 接続が困難な状態を作る |
| 期待動作 | **MID Server を異常検出**（ecc_agent.status が Up 以外: Down / Warning / Disconnected） |
| 対象 MID | stg-1 |
| 計測時間 | 既定 900 秒（推奨） |
| 合否基準 | ServiceNow 上で MID の `status` が Up 以外に 1 回以上変化すること |

## ulimit ではなく sysctl で攻める理由

- `ulimit -n` は **シェルから起動するプロセスにしか効かない** ため、systemd で起動済みの MID daemon の fd 上限には影響しない
- 私たちが本当に枯渇させたいのは **OS グローバルの ephemeral port pool** (`/proc/sys/net/ipv4/ip_local_port_range`)
- これを sysctl で 30 ポート程度に縮小すれば、**MID daemon、Zabbix、その他あらゆるプロセス** が新規 outbound 接続を作れなくなる
- 既存接続が切れて MID が再接続を試みる瞬間に詰まる → ServiceNow 上で MID Down が検知される

## 動作シーケンス

```
1. 現在の ip_local_port_range を /tmp/n5_orig_range に保存
2. sudo sysctl -w net.ipv4.ip_local_port_range="32768 32800"   (33 ポート)
3. Phase 1: Python で 33 ポートを一気に取り尽くす
4. Phase 2: DURATION 秒間、解放されたポートを高速に奪い続ける
5. 番犬プロセス (DURATION+60s で自動復旧) をバックグラウンドに置く
6. 正常終了 / Ctrl-C で sysctl を元に戻す
```

## 実行 (2 端末 + 別ルート)

事前に **必ず別経路 (コンソール / 別 SSH セッション) を確保** すること。新規 SSH ログインが当面できなくなります。

### 端末 A (手元) — MID Status 監視

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
python3 N-common/verify_mid_status.py \
    --duration 900 \
    --mid-name mid-server-aws-zabbix-stg-1 \
    --output N-5/result_mid_status.json
```

`Enter で計測開始 >` で待機。

### 端末 B (MID Server stg-1, sudo 可能なシェル)

```bash
# 事前に sudo を有効化 (パスワード入力)
sudo -v

# 起動 (推奨 900 秒)
bash /tmp/stress_tcp.sh 900

# より厳しく (23 ポートに絞る)
NEW_RANGE="32768 32790" bash /tmp/stress_tcp.sh 900
```

両端末が動き始めたら手元で Enter。

## 出力

`N-5/result_mid_status.json` … 観測した status の一覧、初回異常検出時刻、判定

## 緊急時の復旧（kill -9 された場合）

スクリプトは終了 trap で sysctl を元に戻すが、kill -9 では trap が動かない。
番犬プロセスが `DURATION + 60秒` で自動復旧するが、手動で即時復旧したい場合:

```bash
# /tmp/n5_orig_range に元値が保存されている
sudo sysctl -w net.ipv4.ip_local_port_range="$(cat /tmp/n5_orig_range)"
rm -f /tmp/n5_orig_range
```

## 注意

- 縮小中は **OS 上の他プロセス** も新規 outbound 接続が事実上不可になる
  - DNS 解決、新規 SSH、外部 API 呼び出し 等
- **既存接続** は影響なし（既に確立済みの SSH 等は維持される）
- ServiceNow の MID Down 判定は heartbeat タイムアウト（5〜10 分）に依存するので、`--duration 900` 以上を推奨
