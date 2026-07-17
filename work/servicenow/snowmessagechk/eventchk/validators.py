"""
仕様書「確定版Log → Event」シートに基づくイベントフィールド検証ロジック。
データソースを source フィールドで識別し、各ソース専用のルールでチェックする。
"""

from dataclasses import dataclass, field
from typing import Optional


# em_event.severity の数値 → 日本語ラベル
SEVERITY_MAP = {
    "0": "クリア",
    "1": "重大",
    "2": "重要",
    "3": "マイナー",
    "4": "警告",
    "5": "情報",
}

# 仕様書 Max length 列より
MAX_LEN = {
    "source":          200,
    "node":            100,
    "type":            100,
    "resource":        100,
    "metric_name":    1024,
    "event_class":     100,
    "message_key":    1024,
    "description":    4000,
    "additional_info": 4000,
}


@dataclass
class CheckResult:
    field: str
    status: str       # "OK" / "NG" / "WARN"
    expected: str
    actual: str
    message: str = ""


@dataclass
class EventResult:
    sys_id: str
    source: str
    source_type: str
    status: str       # "OK" / "NG" / "UNKNOWN_SOURCE"
    checks: list = field(default_factory=list)

    @property
    def ng_count(self):
        return sum(1 for c in self.checks if c.status == "NG")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _get_str(event: dict, fname: str) -> str:
    """display_value=true 時の辞書・文字列両対応で値を取り出す。"""
    val = event.get(fname, "")
    if isinstance(val, dict):
        return str(val.get("value") or val.get("display_value") or "")
    return str(val or "")


def normalize_severity(val: str) -> str:
    """重大度値を 0-5 の文字列に正規化する。"""
    if not val:
        return ""
    s = val.strip()
    if s.isdigit():
        return s
    # "1 - Critical" パターン
    parts = s.split()
    if parts and parts[0].isdigit():
        return parts[0]
    # 日本語ラベル逆引き
    rev = {v: k for k, v in SEVERITY_MAP.items()}
    return rev.get(s, s)


def _check_nonempty(event: dict, fname: str, label: str) -> CheckResult:
    val = _get_str(event, fname)
    if val and val not in ("null", ""):
        return CheckResult(fname, "OK", f"{label}が設定されている", val[:100])
    return CheckResult(fname, "NG", f"{label}が設定されている", "", f"{label}が空です")


def _check_empty(event: dict, fname: str, label: str) -> CheckResult:
    """このソースでは使用しないフィールドが空かを確認する。"""
    val = _get_str(event, fname)
    if not val or val in ("null", ""):
        return CheckResult(fname, "OK", f"{label}=空(未使用)", "")
    return CheckResult(fname, "WARN", f"{label}=空(未使用)", val[:100],
                       f"このソースでは{label}は未使用ですが値があります")


def _check_metric_name_expanded(event: dict) -> CheckResult | None:
    """変換スクリプトのテンプレート変数が未展開のまま残っている場合を検出する。
    例: <'{Trigger[MetricName"]}':UNKNOWN>" → 変換スクリプトの変数名誤り。
    正常値の場合は None を返す（追加チェック不要）。"""
    val = _get_str(event, "metric_name")
    if "':UNKNOWN>" in val:
        return CheckResult("metric_name", "NG",
                           "テンプレート変数が展開された正常値",
                           val[:80],
                           "変換スクリプトの変数名誤り（テンプレート未展開）")
    return None


def _check_source_value(event: dict, expected: str) -> CheckResult:
    actual = _get_str(event, "source")
    if actual == expected:
        return CheckResult("source", "OK", expected, actual)
    return CheckResult("source", "NG", expected, actual, "ソース値が仕様と不一致")


def _check_severity_in(event: dict, allowed: tuple, note: str) -> CheckResult:
    val = _get_str(event, "severity")
    norm = normalize_severity(val)
    labels = "/".join(f"{n}({SEVERITY_MAP.get(n,n)})" for n in allowed)
    if norm in allowed:
        return CheckResult("severity", "OK", labels, val)
    return CheckResult("severity", "NG", labels, val, note)


def _maxlen_checks(event: dict, warn_fields: frozenset = frozenset()) -> list:
    """warn_fields に含まれるフィールドは超過時に NG でなく WARN にする。"""
    results = []
    for fname, limit in MAX_LEN.items():
        val = _get_str(event, fname)
        if len(val) > limit:
            status = "WARN" if fname in warn_fields else "NG"
            results.append(CheckResult(
                fname, status,
                f"最大{limit}文字以内",
                val[:60] + "...",
                f"文字数超過: {len(val)}文字"
            ))
    return results


# ---------------------------------------------------------------------------
# ソース別バリデーター
# ---------------------------------------------------------------------------

def _base(event, source_chk, nonempty_fields, empty_fields, sev_check,
          warn_maxlen_fields: frozenset = frozenset()):
    r = [source_chk]
    for fname, label in nonempty_fields:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in empty_fields:
        r.append(_check_empty(event, fname, label))
    r.append(sev_check)
    r += _maxlen_checks(event, warn_maxlen_fields)
    return r


def validate_cloudwatch(event):
    r = _base(
        event,
        _check_source_value(event, "CloudWatchLogs"),
        [("node", "ノード"), ("resource", "リソース"), ("metric_name", "メトリクス名"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [],
        _check_severity_in(event, ("1", "2", "3", "4", "5"),
                           "ALARM+critical→重大(1), ALARM+warn→重要(2), OK→情報(5), INSUFFICIENT_DATA→マイナー(3), 警告(4)も許容")
    )
    extra = _check_metric_name_expanded(event)
    if extra:
        r.append(extra)
    return r


def validate_cloudwatch_hios(event):
    # ログベースアラームのため MetricName が構造的に存在しない。全件空が正常のためチェック対象外
    return _base(
        event,
        _check_source_value(event, "CloudWatchLogs(HIOS)"),
        [("node", "ノード"), ("resource", "リソース"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [],
        _check_severity_in(event, ("1", "2", "3", "4", "5"),
                           "ALARM+critical→重大(1), ALARM+warn→重要(2), OK→情報(5), INSUFFICIENT_DATA→マイナー(3), 警告(4)も許容")
    )


def validate_rds(event):
    return _base(
        event,
        _check_source_value(event, "RDS"),
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("1", "2", "3", "5"),
                           "shutdown/failover→重大(1), 復旧→情報(5), その他→重要(2), マイナー(3)も許容（INSUFFICIENT_DATA等）")
    )


def validate_hios_aws(event):
    r = _base(
        event,
        _check_source_value(event, "HIOS(AWS)"),
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("2", "4"), "重要(2) または 警告(4)（サーバリブートは警告(4)）")
    )
    return r


def validate_imark_aws(event):
    r = _base(
        event,
        _check_source_value(event, "Trap From Enterprise 119"),
        [("node", "ノード"), ("message_key", "メッセージキー"),
         ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("1", "3"), "HighImpact→重大(1), NoImpact→マイナー(3)")
    )
    additional = _get_str(event, "additional_info")
    if ".119.1.107.300.6" in additional:
        r.append(CheckResult("additional_info[enterprise]", "OK", "OID .119.1.107.300.6を含む", "確認"))
    else:
        r.append(CheckResult("additional_info[enterprise]", "NG", "OID .119.1.107.300.6を含む",
                             "未検出", "iMark(AWS)のエンタープライズOIDが見つかりません"))
    return r


def validate_dead_letter_queue(event):
    return _base(
        event,
        _check_source_value(event, "Dead Letter Queue"),
        [("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("node", "ノード(空欄)"), ("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("2", "5"), "ALARM→重要(2), OK→情報(5)")
    )


def validate_imark_sv(event):
    r = _base(
        event,
        _check_source_value(event, "Trap From Enterprise 119"),
        [("node", "ノード"), ("message_key", "メッセージキー"),
         ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("1", "2", "3", "4"), "重大(1)/重要(2)/マイナー(3)/警告(4)（実態に合わせて拡張）")
    )
    additional = _get_str(event, "additional_info")
    if ".119.1.107.300.1" in additional:
        r.append(CheckResult("additional_info[enterprise]", "OK", "OID .119.1.107.300.1を含む", "確認"))
    else:
        r.append(CheckResult("additional_info[enterprise]", "NG", "OID .119.1.107.300.1を含む",
                             "未検出", "iMark(SV)のエンタープライズOIDが見つかりません"))
    return r


def validate_snmptrap(event):
    # message_key / severity は Event→Alert 処理時に設定されるため em_event 段階ではチェック対象外
    r = [_check_source_value(event, "SNMPv2 Generic Trap")]
    for fname, label in [("node", "ノード"), ("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r += _maxlen_checks(event)
    return r


def validate_trap674(event):
    # Dell iDRAC SNMPトラップ。message_key/severity は Event→Alert 処理時に設定されるため em_event 段階ではチェック対象外
    r = [_check_source_value(event, "Trap From Enterprise 674")]
    for fname, label in [("node", "ノード"), ("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r += _maxlen_checks(event)
    return r


def validate_trap3375(event):
    # F5 BIG-IP SNMPトラップ。node は構造的に空（BIG-IPトラップの仕様）。message_key/severity は Event→Alert 処理時に設定
    r = [_check_source_value(event, "Trap From Enterprise 3375")]
    for fname, label in [("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r += _maxlen_checks(event)
    return r


def validate_trap22610(event):
    # A10 Networks SNMPトラップ。message_key/severity は Event→Alert 処理時に設定されるため em_event 段階ではチェック対象外
    r = [_check_source_value(event, "Trap From Enterprise 22610")]
    for fname, label in [("node", "ノード"), ("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r += _maxlen_checks(event)
    return r


def validate_nnmi(event):
    return _base(
        event,
        _check_source_value(event, "NNMi"),
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("2", "5"), "HighImpact→重要(2), NoImpact→情報(5)")
    )


def validate_hios_sv(event):
    return _base(
        event,
        _check_source_value(event, "HIOS(SV)"),
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("2", "3", "4", "5"),
                           "危険/重要警戒域→重要(2), 警戒/注意域→マイナー(3), 警告(4)も許容, 正常域→情報(5)")
    )


def validate_zabbix(event):
    # Zabbix の additional_info は event 情報を多数含み 4000文字超えが想定される仕様のため WARN 扱い
    r = _base(
        event,
        _check_source_value(event, "Zabbix"),
        [("node", "ノード"), ("metric_name", "メトリクス名(item.name)"),
         ("event_class", "ソースインスタンス(Zabbix ○○本番)"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース")],
        _check_severity_in(event, ("0", "1", "2", "3", "4", "5"),
                           "Zabbix優先度 5→重大(1), 4→重要(2), 3→マイナー(3), 2→警告(4), 1/0→情報(5)/マイナー(3), 復旧→クリア(0)OK"),
        warn_maxlen_fields=frozenset({"additional_info"}),
    )
    ec = _get_str(event, "event_class")
    if "Zabbix" not in ec:
        r.append(CheckResult("event_class[Zabbix]", "NG", "値に'Zabbix'を含む", ec[:80],
                             "ソースインスタンスは 'Zabbix 神奈川本番' 等の形式のはず"))
    return r


def validate_syslog(event):
    return _base(
        event,
        _check_source_value(event, "syslog"),
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("resource", "リソース"), ("metric_name", "メトリクス名")],
        _check_severity_in(event, ("1", "2"),
                           "direction:syslog→重大(1), criticalから始まる件名→重要(2)")
    )


def validate_prtg(event):
    return _base(
        event,
        _check_source_value(event, "PRTG"),
        [("node", "ノード"), ("resource", 'リソース(event["name"])'),
         ("metric_name", 'メトリクス名(event["tags"])'), ("event_class", "ソースインスタンス(PRTG_BIGLOBE等)"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [],
        _check_severity_in(event, ("1", "2", "4", "5"),
                           "Down→重大(1), DownPartial→重要(2), Paused*/Unknown/Warning→警告(4), Up/Active→情報(5)")
    )


def _validate_carrier(event, source_val: str) -> list:
    # キャリア障害系共通: node は構造的に空。severity はマイナー(3)固定
    r = [_check_source_value(event, source_val)]
    for fname, label in [("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r.append(_check_severity_in(event, ("3",), "マイナー(3)固定"))
    r += _maxlen_checks(event)
    return r


def _validate_mail_notification(event, source_val: str) -> list:
    # メール由来通知系共通: node は構造的に空。severity はマイナー(3)固定
    r = [_check_source_value(event, source_val)]
    for fname, label in [("event_class", "ソースインスタンス"), ("message_key", "メッセージキー"),
                          ("description", "説明"), ("additional_info", "追加情報")]:
        r.append(_check_nonempty(event, fname, label))
    for fname, label in [("resource", "リソース"), ("metric_name", "メトリクス名")]:
        r.append(_check_empty(event, fname, label))
    r.append(_check_severity_in(event, ("3",), "マイナー(3)固定"))
    r += _maxlen_checks(event)
    return r


def validate_carrier_hikari(event):
    return _validate_carrier(event, "キャリア障害(光回線)")


def validate_carrier_gas(event):
    return _validate_carrier(event, "キャリア障害(GASフィルター後)")


def validate_carrier_type_a(event):
    return _validate_carrier(event, "キャリア障害(type A)")


def validate_triple_error(event):
    return _validate_mail_notification(event, "Triplエラー")


def validate_downdetector(event):
    # node/type は旧フォーマットでは空の場合があるため必須チェック対象外
    return _base(
        event,
        _check_source_value(event, "Downdetector"),
        [("resource", "リソース"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [("metric_name", "メトリクス名")],
        _check_severity_in(event, ("3", "4"), "マイナー(3) または 警告(4)")
    )


def validate_jpix(event):
    return _validate_mail_notification(event, "JPIX")


def validate_weathernews(event):
    return _validate_mail_notification(event, "ウェザーニューズ")


def validate_em_self_monitoring(event):
    # ServiceNow EM 自己監視イベント。実態に合わせて全severity値を許容
    return _base(
        event,
        _check_source_value(event, "EMSelfMonitoring"),
        [("type", "タイプ"), ("resource", "リソース"), ("metric_name", "メトリクス名"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        [],
        _check_severity_in(event, ("1", "2", "3", "4", "5"), "重大(1)/重要(2)/マイナー(3)/警告(4)/情報(5)")
    )


# ---------------------------------------------------------------------------
# ソース識別テーブル
# ---------------------------------------------------------------------------

SOURCE_VALIDATORS = {
    "1-1 CloudWatch":        validate_cloudwatch,
    "1-2 RDS":               validate_rds,
    "1-3 HIOS(AWS)":         validate_hios_aws,
    "1-4 CloudWatch(HIOS)":  validate_cloudwatch_hios,
    "1-5 iMark(AWS)":        validate_imark_aws,
    "1-6 Dead Letter Queue": validate_dead_letter_queue,
    "2-1 iMark(SV)":         validate_imark_sv,
    "2-2 snmptrap":          validate_snmptrap,
    "HW-674 Dell iDRAC":    validate_trap674,
    "HW-3375 BIG-IP":       validate_trap3375,
    "HW-22610 A10":         validate_trap22610,
    "2-3 NNMi":              validate_nnmi,
    "2-4,2-5 HIOS(SV)":      validate_hios_sv,
    "3-1 Zabbix":            validate_zabbix,
    "3-3 syslog":            validate_syslog,
    "PRTG":                  validate_prtg,
    "キャリア障害(光回線)":        validate_carrier_hikari,
    "キャリア障害(GASフィルター後)": validate_carrier_gas,
    "キャリア障害(type A)":      validate_carrier_type_a,
    "Triplエラー":              validate_triple_error,
    "Downdetector":            validate_downdetector,
    "JPIX":                    validate_jpix,
    "ウェザーニューズ":            validate_weathernews,
    "EMSelfMonitoring":        validate_em_self_monitoring,
}


def identify_source(event: dict) -> str:
    src = _get_str(event, "source")

    if src == "CloudWatchLogs(HIOS)":
        return "1-4 CloudWatch(HIOS)"
    if src == "CloudWatchLogs":
        return "1-1 CloudWatch"
    if src == "RDS":
        return "1-2 RDS"
    if src == "HIOS(AWS)":
        return "1-3 HIOS(AWS)"
    if src == "Trap From Enterprise 119":
        # additional_info のエンタープライズ OID で iMark(AWS) / iMark(SV) を区別
        ai = _get_str(event, "additional_info")
        if ".119.1.107.300.6" in ai:
            return "1-5 iMark(AWS)"
        if ".119.1.107.300.1" in ai:
            return "2-1 iMark(SV)"
        return "1-5/2-1 iMark(OID不明)"
    if src == "Dead Letter Queue":
        return "1-6 Dead Letter Queue"
    if src == "SNMPv2 Generic Trap":
        return "2-2 snmptrap"
    if src == "Trap From Enterprise 674":
        return "HW-674 Dell iDRAC"
    if src == "Trap From Enterprise 3375":
        return "HW-3375 BIG-IP"
    if src == "Trap From Enterprise 22610":
        return "HW-22610 A10"
    if src == "NNMi":
        return "2-3 NNMi"
    if src == "HIOS(SV)":
        return "2-4,2-5 HIOS(SV)"
    if src == "Zabbix":
        return "3-1 Zabbix"
    if src == "syslog":
        return "3-3 syslog"
    if src == "PRTG":
        return "PRTG"
    if src == "キャリア障害(光回線)":
        return "キャリア障害(光回線)"
    if src == "キャリア障害(GASフィルター後)":
        return "キャリア障害(GASフィルター後)"
    if src == "キャリア障害(type A)":
        return "キャリア障害(type A)"
    if src == "Triplエラー":
        return "Triplエラー"
    if src == "Downdetector":
        return "Downdetector"
    if src == "JPIX":
        return "JPIX"
    if src == "ウェザーニューズ":
        return "ウェザーニューズ"
    if src == "EMSelfMonitoring":
        return "EMSelfMonitoring"
    return "UNKNOWN"


def validate_event(event: dict) -> EventResult:
    source_str = _get_str(event, "source")
    source_type = identify_source(event)
    sys_id = _get_str(event, "sys_id")

    validator = SOURCE_VALIDATORS.get(source_type)
    if not validator:
        return EventResult(
            sys_id=sys_id,
            source=source_str,
            source_type=source_type,
            status="UNKNOWN_SOURCE",
            checks=[CheckResult("source", "NG", "既知のソース値",
                                source_str, f"未定義ソース: '{source_str}'")]
        )

    checks = validator(event)
    has_ng = any(c.status == "NG" for c in checks)
    return EventResult(
        sys_id=sys_id,
        source=source_str,
        source_type=source_type,
        status="NG" if has_ng else "OK",
        checks=checks,
    )
