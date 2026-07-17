#!/usr/bin/env python3
"""
Zabbix ホスト大量コピースクリプト (アイテム・トリガーコピー対応版)
元ホスト: test-servicenow-monohyouka-1
コピー先: test-servicenow-monohyouka-00001 ～ test-servicenow-monohyouka-30000
"""

import os
import requests
import sys
import time
import argparse
import urllib3
from pathlib import Path
from typing import Any

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# .env から認証情報を読み込む (リポジトリ共通の kakusyou/.env)
# python-dotenv が無い環境でも動くよう try/except で吸収する
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

# =============================================
# 設定
# =============================================
# 認証情報は環境変数 / .env から取得する (ハードコード禁止・git 登録防止)
ZABBIX_URL        = os.getenv("ZABBIX_URL", "https://10.249.73.66/zabbix/api_jsonrpc.php")
ZABBIX_USER       = os.getenv("ZABBIX_USER", "")
ZABBIX_PASS       = os.getenv("ZABBIX_PASSWORD", "")

SOURCE_HOST_NAME  = "test-servicenow-monohyouka-1"
DEST_HOST_PREFIX  = "test-servicenow-monohyouka-"
COPY_COUNT        = 30000
BATCH_SIZE        = 50
SLEEP_BETWEEN_BATCH = 0.5


# =============================================
# Zabbix API
# =============================================
class ZabbixAPI:
    def __init__(self, url):
        self.url = url
        self.auth_token = None
        self.req_id = 1

    def call(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": self.req_id}
        if self.auth_token:
            payload["auth"] = self.auth_token
        self.req_id += 1
        r = requests.post(self.url, json=payload,
                          headers={"Content-Type": "application/json"},
                          verify=False, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")
        return data["result"]

    def login(self, user, password):
        self.auth_token = self.call("user.login", {"user": user, "password": password})
        print("[OK] ログイン成功")

    def logout(self):
        if self.auth_token:
            self.call("user.logout", [])
            self.auth_token = None


# =============================================
# ホスト情報取得
# =============================================
def get_source_host(zapi, hostname):
    result = zapi.call("host.get", {
        "filter": {"host": hostname},
        "selectGroups": "extend",
        "selectTemplates": "extend",
        "selectInterfaces": "extend",
        "selectMacros": "extend",
        "selectTags": "extend",
        "selectInventory": "extend",
        "output": "extend",
    })
    if not result:
        raise ValueError(f"ホストが見つかりません: {hostname}")
    return result[0]


def get_custom_items(zapi, hostid):
    return zapi.call("item.get", {
        "hostids": hostid,
        "inherited": False,
        "output": "extend",
    })


def get_custom_triggers(zapi, hostid):
    """
    トリガーを取得。selectFunctions でfunctionid→(itemid,function,parameter)を取得する。
    これによりexpressionを正しく組み立て直せる。
    """
    return zapi.call("trigger.get", {
        "hostids": hostid,
        "inherited": False,
        "selectFunctions": "extend",   # functionidの詳細
        "selectTags": "extend",
        "output": "extend",
    })


def get_existing_hosts(zapi, prefix):
    result = zapi.call("host.get", {
        "search": {"host": prefix},
        "startSearch": True,
        "output": ["hostid", "host"],
    })
    return {h["host"]: h["hostid"] for h in result}


# =============================================
# ホスト作成
# =============================================
ITEM_SKIP = {"itemid", "hostid", "templateid", "uuid", "state", "error",
             "lastclock", "lastns", "lastvalue", "prevvalue", "flags"}

def build_host_payload(source, new_name):
    groups    = [{"groupid": g["groupid"]} for g in source.get("groups", [])]
    templates = [{"templateid": t["templateid"]} for t in source.get("parentTemplates", [])]
    interfaces = [{k: v for k, v in i.items() if k not in ("interfaceid", "hostid")}
                  for i in source.get("interfaces", [])]
    macros    = [{k: v for k, v in m.items() if k not in ("hostmacroid", "hostid")}
                 for m in source.get("macros", [])]
    tags      = [{"tag": t["tag"], "value": t.get("value", "")} for t in source.get("tags", [])]

    payload = {
        "host": new_name, "name": new_name,
        "status": source.get("status", "0"),
        "groups": groups, "interfaces": interfaces, "tags": tags,
    }
    if templates: payload["templates"] = templates
    if macros:    payload["macros"] = macros
    if source.get("proxy_hostid") and source["proxy_hostid"] != "0":
        payload["proxy_hostid"] = source["proxy_hostid"]
    if source.get("inventory") and isinstance(source["inventory"], dict):
        inv = {k: v for k, v in source["inventory"].items() if v}
        if inv:
            payload["inventory_mode"] = source.get("inventory_mode", "0")
            payload["inventory"] = inv
    return payload


# =============================================
# アイテム・トリガーコピー
# =============================================
def rebuild_expression(expression, functions, src_itemid_to_dst_itemname, dst_host_name):
    """
    Zabbix 6.0 の {functionid} 形式のexpressionを
    last(/ホスト名/アイテムキー) 形式に書き直す。

    例:
      expression = "{74622}=1"
      functions  = [{"functionid":"74622","itemid":"85197","function":"last","parameter":"$"}]
      src_itemid_to_dst_itemname = {"85197": "test-hyoka"}
      dst_host_name = "test-servicenow-monohyouka-00001"
      結果: "last(/test-servicenow-monohyouka-00001/test-hyoka)=1"
    """
    result = expression
    for func in functions:
        func_id  = func["functionid"]   # 例: "74622"
        src_item = func["itemid"]       # 例: "85197"
        fn_name  = func["function"]     # 例: "last"
        param    = func["parameter"]    # 例: "$"
        item_key = src_itemid_to_dst_itemname.get(src_item)
        if not item_key:
            continue

        old_token = f"{{{func_id}}}"
        # param が "$" の場合は省略、それ以外はそのまま使用
        if param == "$":
            new_token = f"{fn_name}(/{dst_host_name}/{item_key})"
        else:
            new_token = f"{fn_name}(/{dst_host_name}/{item_key},{param})"
        result = result.replace(old_token, new_token)

    return result


def copy_items_and_triggers(zapi, src_items, src_triggers, dst_hostid, dst_host_name):
    """
    1. アイテムをコピーして src_itemid→item_key マップを作成
    2. expressionを last(/ホスト名/キー) 形式に書き直してトリガーを作成
    戻り値: (作成トリガー数, スキップトリガー数)
    """

    # --- 1. アイテムのコピー & src_itemid→item_key マップ作成 ---
    existing_items_raw = zapi.call("item.get", {
        "hostids": dst_hostid,
        "output": ["itemid", "key_"],
    })
    existing_keys = {i["key_"] for i in existing_items_raw}

    # src_itemid → item_key_ (アイテムキーはコピー元もコピー先も同じ)
    src_itemid_to_key = {}
    for item in src_items:
        src_id  = item["itemid"]
        src_key = item["key_"]
        src_itemid_to_key[src_id] = src_key  # キーは変わらない

        if src_key not in existing_keys:
            payload = {k: v for k, v in item.items() if k not in ITEM_SKIP}
            payload["hostid"] = dst_hostid
            try:
                zapi.call("item.create", payload)
                existing_keys.add(src_key)
            except Exception as e:
                print(f"    [WARN] アイテム作成失敗 '{src_key}': {e}")

    # --- 2. 既存トリガー確認（重複防止） ---
    existing_triggers_raw = zapi.call("trigger.get", {
        "hostids": dst_hostid,
        "inherited": False,
        "output": ["description"],
    })
    existing_descs = {t["description"] for t in existing_triggers_raw}

    # --- 3. トリガーのコピー ---
    created = 0
    skipped = 0

    for trig in src_triggers:
        desc = trig["description"]

        if desc in existing_descs:
            skipped += 1
            continue

        functions = trig.get("functions", [])

        # expressionを last(/ホスト名/キー) 形式に書き直す
        expr     = rebuild_expression(trig.get("expression", ""),          functions, src_itemid_to_key, dst_host_name)
        recovery = rebuild_expression(trig.get("recovery_expression", ""), functions, src_itemid_to_key, dst_host_name)

        tags = [{"tag": t["tag"], "value": t.get("value", "")}
                for t in trig.get("tags", [])]

        payload = {
            "description":         desc,
            "expression":          expr,
            "recovery_mode":       trig.get("recovery_mode", "0"),
            "recovery_expression": recovery,
            "correlation_mode":    trig.get("correlation_mode", "0"),
            "correlation_tag":     trig.get("correlation_tag", ""),
            "url":                 trig.get("url", ""),
            "status":              trig.get("status", "0"),
            "priority":            trig.get("priority", "0"),
            "comments":            trig.get("comments", ""),
            "type":                trig.get("type", "0"),
            "manual_close":        trig.get("manual_close", "0"),
        }
        if tags:
            payload["tags"] = tags

        try:
            zapi.call("trigger.create", payload)
            created += 1
        except Exception as e:
            print(f"    [WARN] トリガー作成失敗 '{desc}': {e}")
            print(f"           expression: {expr}")

    return created, skipped


# =============================================
# メイン
# =============================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",      default=ZABBIX_URL)
    parser.add_argument("--user",     default=ZABBIX_USER)
    parser.add_argument("--password", default=ZABBIX_PASS)
    parser.add_argument("--source",   default=SOURCE_HOST_NAME)
    parser.add_argument("--count",    type=int, default=COPY_COUNT)
    parser.add_argument("--prefix",   default=DEST_HOST_PREFIX)
    parser.add_argument("--batch",    type=int, default=BATCH_SIZE)
    parser.add_argument("--start",    type=int, default=1)
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    zapi = ZabbixAPI(args.url)

    try:
        zapi.login(args.user, args.password)

        # コピー元取得
        print(f"[INFO] コピー元ホスト取得中: {args.source}")
        source_host = get_source_host(zapi, args.source)
        src_hostid  = source_host["hostid"]
        print(f"[OK] hostid={src_hostid}")
        print(f"     グループ数        : {len(source_host.get('groups', []))}")
        print(f"     テンプレート数    : {len(source_host.get('parentTemplates', []))}")
        print(f"     インターフェース数: {len(source_host.get('interfaces', []))}")

        print(f"\n[INFO] カスタムアイテム取得中...")
        src_items = get_custom_items(zapi, src_hostid)
        print(f"[OK] カスタムアイテム数: {len(src_items)}")
        for i in src_items:
            print(f"     - {i['key_']} ({i['name']})  itemid={i['itemid']}")

        print(f"\n[INFO] カスタムトリガー取得中...")
        src_triggers = get_custom_triggers(zapi, src_hostid)
        print(f"[OK] カスタムトリガー数: {len(src_triggers)}")
        for t in src_triggers:
            print(f"     - [{t.get('priority','0')}] {t['description']}")
            print(f"       expression={t['expression']}")
            for f in t.get("functions", []):
                print(f"       function: {f['functionid']} → itemid={f['itemid']} {f['function']}({f['parameter']})")

        # 既存ホスト確認
        print(f"\n[INFO] 既存コピー先ホスト確認中...")
        existing = get_existing_hosts(zapi, args.prefix)
        existing.pop(args.source, None)
        print(f"[INFO] 既存コピー済みホスト数: {len(existing)}")

        targets      = []
        trigger_only = []
        for i in range(args.start, args.count + 1):
            name = f"{args.prefix}{i:05d}"
            if name in existing:
                trigger_only.append((existing[name], name))
            else:
                targets.append(name)

        print(f"[INFO] 新規作成対象: {len(targets)} 台 / アイテム+トリガーのみ対象: {len(trigger_only)} 台")

        if not targets and not trigger_only:
            print("[INFO] 対象なし。終了します。")
            return

        if args.dry_run:
            print(f"\n[DRY-RUN] 新規作成予定 (先頭10件): {targets[:10]}")
            print(f"[DRY-RUN] トリガーのみ予定 (先頭10件): {[n for _,n in trigger_only[:10]]}")
            print("[DRY-RUN] --dry-run を外して実行してください。")
            return

        # ホスト新規作成
        total_created  = 0
        total_failed   = 0
        total_triggers = 0
        total_skipped  = 0
        failed_names   = []
        created_hosts  = []

        if targets:
            print(f"\n[INFO] ホスト作成開始 (バッチサイズ: {args.batch})")
            print("-" * 60)
            for batch_start in range(0, len(targets), args.batch):
                batch    = targets[batch_start:batch_start + args.batch]
                payloads = [build_host_payload(source_host, n) for n in batch]
                try:
                    hostids = zapi.call("host.create", payloads)["hostids"]
                    total_created += len(hostids)
                    created_hosts.extend(zip(hostids, batch))
                    end_idx = min(batch_start + args.batch, len(targets))
                    print(f"[OK] {batch_start+1:5d} ～ {end_idx:5d} 完了 (累計: {total_created}/{len(targets)})")
                except Exception as e:
                    print(f"[WARN] バッチ失敗、個別作成: {e}")
                    for name in batch:
                        try:
                            hid = zapi.call("host.create", build_host_payload(source_host, name))["hostids"][0]
                            total_created += 1
                            created_hosts.append((hid, name))
                        except Exception as e2:
                            total_failed += 1
                            failed_names.append(name)
                            print(f"[ERROR] {name}: {e2}")
                if batch_start + args.batch < len(targets):
                    time.sleep(SLEEP_BETWEEN_BATCH)
            print("-" * 60)
            print(f"[INFO] ホスト作成完了: {total_created} 台 / 失敗: {total_failed} 台")

        # アイテム+トリガーコピー
        all_targets = created_hosts + trigger_only

        if (src_items or src_triggers) and all_targets:
            print(f"\n[INFO] アイテム+トリガーコピー開始 ({len(all_targets)} 台)")
            print("-" * 60)
            for idx, (dst_hostid, dst_name) in enumerate(all_targets, 1):
                n, s = copy_items_and_triggers(
                    zapi, src_items, src_triggers, dst_hostid, dst_name
                )
                total_triggers += n
                total_skipped  += s
                if idx % 500 == 0 or idx == len(all_targets):
                    print(f"[OK] {idx}/{len(all_targets)} ホスト完了 "
                          f"(トリガー作成: {total_triggers} / スキップ: {total_skipped})")
            print("-" * 60)

        print(f"\n[完了]")
        print(f"  ホスト新規作成  : {total_created} 台 (失敗: {total_failed} 台)")
        print(f"  トリガー新規作成: {total_triggers} 件")
        print(f"  トリガースキップ: {total_skipped} 件 (既存のため)")

        if failed_names:
            with open("failed_hosts.txt", "w") as f:
                f.write("\n".join(failed_names))
            print(f"  失敗ホスト → failed_hosts.txt に保存")

    except Exception as e:
        print(f"\n[FATAL] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        zapi.logout()
        print("[INFO] ログアウト完了")


if __name__ == "__main__":
    main()
