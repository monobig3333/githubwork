# 2-2 アラーム処理性能（最大負荷 30,000件/10分）

## 試験方式

評価環境の Zabbix は **6.0**（`history.push` API なし）かつ、
ネットワークが **HTTPS 443 のみ通信可** という二重制約あり。

そこで「Zabbix サーバ上で `zabbix_sender` を実行する Script」を
Zabbix UI に登録しておき、`script.execute` API（HTTPS）で呼び出す方式を採用。

```
┌────────┐  HTTPS API     ┌─────────┐  localhost 10051  ┌──────────┐
│ Python │ ──────────────→│ Zabbix  │ ─────────────────→│ trapper  │
│ (Mac)  │ script.execute │ Server  │ (Zabbix server 内) │ item     │
└────────┘                └─────────┘                    └──────────┘
   Mac 側は完全に HTTPS のみ                              │
                                                          ▼
                                                       Trigger → MID → ServiceNow
```

| 項目 | 内容 |
|---|---|
| ツール | Python `2-2/zabbix_load.py` + Zabbix HTTPS API |
| 通信 | HTTPS 443 のみ（Mac 側） |
| 投入量 | 30,000 件 / 10 分 (= 50 req/s) |
| 合否基準 | API 成功率 100%、ServiceNow em_event に全件受信 |

## 前準備（Zabbix 管理者）

Zabbix UI で **Scripts** を作成（一度だけ）:

```
Administration → Scripts → Create script

Name:           PerfTest SendValue
Scope:          Manual host action
Type:           Script
Execute on:     Zabbix server
Commands:
  /usr/bin/zabbix_sender -z 127.0.0.1 \
    -s "{HOST.HOST}" -k "test-hyoka" -o "1"
Host group:     All hosts (または test-servicenow-monohyouka-* を含むグループ)
User group:     Zabbix administrators
Confirmation:   (空欄)
```

作成後、**scriptid を控える** （URL の `scriptid=...` か、API で確認）。

API で scriptid を取得したい場合、本スクリプトに `--list-scripts` オプションあり:

```bash
python3 2-2/zabbix_load.py --list-scripts
```

## セットアップ

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` を編集:

```dotenv
ZABBIX_URL=https://10.249.73.66/zabbix/api_jsonrpc.php
ZABBIX_USER=mono
ZABBIX_PASSWORD=...
ZABBIX_SCRIPT_ID=<前準備で控えた script の sysid>
ZABBIX_HOST_PREFIX=test-servicenow-monohyouka-
ZABBIX_VERIFY_TLS=false
```

## 動作確認手順

```bash
# 1) 登録済みスクリプト一覧を確認（script_id を見つける）
python3 2-2/zabbix_load.py --list-scripts

# 2) dry-run（接続テスト + 対象ホスト確認）
python3 2-2/zabbix_load.py --total 10 --dry-run

# 3) 軽量スモーク（10件、5 req/s）
python3 2-2/zabbix_load.py --total 10 --rate 5

# 4) 100件で挙動確認
python3 2-2/zabbix_load.py --start 1 --end 100 --total 100 --rate 50

# 5) 本番（30000件 / 50 req/s = 10分）
python3 2-2/zabbix_load.py --total 30000 --rate 50
```

## 投入後の受信確認（ServiceNow 側）

```bash
HOST=biglobenonprod.service-now.com
TOKEN=$(curl -s -u "$CID:$SEC" -d 'grant_type=client_credentials' \
  "https://$HOST/oauth_token.do" | jq -r '.access_token')

# 直近1時間の test-servicenow-monohyouka 関連イベント件数
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://$HOST/api/now/stats/em_event?sysparm_count=true&sysparm_query=nodeSTARTSWITHtest-servicenow-monohyouka%5Esys_created_on>=javascript:gs.beginningOfLastHour()" \
  | jq .
```

期待: `count` が 30,000 件前後。

## 結果ファイル

`2-2/result_2_2.json`:

```json
{
  "method": "script.execute via Zabbix HTTPS API",
  "total": 30000,
  "success": 30000,
  "failed": 0,
  "elapsed_sec": 605.3,
  "effective_rps": 49.5,
  "target_rps": 50.0
}
```

## トラブルシュート

| 症状 | 原因 | 対処 |
|---|---|---|
| `ZABBIX_SCRIPT_ID is not set` | .env 未設定 | `--list-scripts` で確認・設定 |
| `script.execute: Permission denied` | ユーザがスクリプト実行権限なし | Zabbix admin にユーザグループ追加依頼 |
| `Host not found` | ホスト名フォーマットずれ | `ZABBIX_HOST_FORMAT` で書式調整 |
| `Cannot execute on Zabbix proxy` | スクリプトの Execute on 設定ミス | UI で `Zabbix server` に変更 |
| ServiceNow に届かない | Zabbix トリガー未発火 / MID 設定 | Zabbix UI でトリガー状態確認 |
