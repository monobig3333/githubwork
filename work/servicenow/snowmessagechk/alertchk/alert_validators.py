"""
仕様書「イベントルール・アラート管理ルール設計書.xlsx」イベントルールシートに基づく
em_alert フィールド検証ロジック。

イベントルールによって em_event → em_alert 変換後のアラートを検証する。
識別キー: em_alert.source（変換後ソース値）+ resource（HW監視系の区別に使用）
"""

from dataclasses import dataclass, field


# em_alert.severity の数値 → 日本語ラベル（em_event と同じマッピング）
SEVERITY_MAP = {
    "0": "クリア",
    "1": "重大",
    "2": "重要",
    "3": "マイナー",
    "4": "警告",
    "5": "情報",
}

# em_alert のカスタムフィールド名マッピング
# ※実際の ServiceNow インスタンスのフィールド名と異なる場合は調整すること
FIELD_TYPE_BIG = "u_type_category"      # タイプ(大分類): AWS / SV / NW（実フィールド名確認済み）
FIELD_MATCHED_RULES = "u_matched_rules" # マッチしたルール名

MAX_LEN = {
    "node":            255,
    "type":            100,
    "resource":        255,
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
class AlertResult:
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

def _get_str(rec: dict, fname: str) -> str:
    """display_value=true 時の辞書・文字列両対応で値を取り出す。"""
    val = rec.get(fname, "")
    if isinstance(val, dict):
        return str(val.get("value") or val.get("display_value") or "")
    return str(val or "")


def _normalize_sev(val: str) -> str:
    if not val:
        return ""
    s = val.strip()
    if s.isdigit():
        return s
    parts = s.split()
    if parts and parts[0].isdigit():
        return parts[0]
    rev = {v: k for k, v in SEVERITY_MAP.items()}
    return rev.get(s, s)


def _chk_nonempty(rec: dict, fname: str, label: str) -> CheckResult:
    val = _get_str(rec, fname)
    if val and val not in ("null", ""):
        return CheckResult(fname, "OK", f"{label}が設定されている", val[:100])
    return CheckResult(fname, "NG", f"{label}が設定されている", "", f"{label}が空です")


def _chk_literal(rec: dict, fname: str, expected: str) -> CheckResult:
    actual = _get_str(rec, fname)
    if actual == expected:
        return CheckResult(fname, "OK", expected, actual)
    return CheckResult(fname, "NG", expected, actual[:100], "仕様値と不一致")


def _chk_sev_in(rec: dict, allowed: tuple, note: str) -> CheckResult:
    val = _get_str(rec, "severity")
    norm = _normalize_sev(val)
    labels = "/".join(f"{n}({SEVERITY_MAP.get(n, n)})" for n in allowed)
    if norm in allowed:
        return CheckResult("severity", "OK", labels, val)
    return CheckResult("severity", "NG", labels, val, note)


def _chk_maxlen_list(rec: dict, warn_fields: frozenset = frozenset()) -> list:
    """warn_fields に含まれるフィールドは超過時に NG でなく WARN にする。"""
    results = []
    for fname, limit in MAX_LEN.items():
        val = _get_str(rec, fname)
        if len(val) > limit:
            status = "WARN" if fname in warn_fields else "NG"
            results.append(CheckResult(
                fname, status,
                f"最大{limit}文字以内",
                val[:60] + "...",
                f"文字数超過: {len(val)}文字"
            ))
    return results


def _chk_metric_name_expanded(rec: dict) -> CheckResult | None:
    """テンプレート変数が未展開のまま残っている場合を検出する。"""
    val = _get_str(rec, "metric_name")
    if "':UNKNOWN>" in val:
        return CheckResult("metric_name", "NG",
                           "テンプレート変数が展開された正常値",
                           val[:80],
                           "変換スクリプトの変数名誤り（テンプレート未展開）")
    return None


def _chk_type_big(rec: dict, expected: str) -> CheckResult:
    actual = _get_str(rec, FIELD_TYPE_BIG)
    if actual == expected:
        return CheckResult(FIELD_TYPE_BIG, "OK", expected, actual)
    if not actual:
        # フィールド未取得の可能性があるため WARN に留める
        return CheckResult(FIELD_TYPE_BIG, "WARN", expected, "",
                           f"フィールド {FIELD_TYPE_BIG!r} が空（フィールド名を確認してください）")
    return CheckResult(FIELD_TYPE_BIG, "NG", expected, actual, "タイプ(大分類)が仕様値と不一致")


# ---------------------------------------------------------------------------
# ソース別バリデーター
# ---------------------------------------------------------------------------

def validate_imark_aws(rec: dict) -> list:
    """Trap 119 + OID .300.6 → iMark_AWS ルール処理後アラート。"""
    return [
        _chk_literal(rec, "source", "iMark_AWS"),
        _chk_literal(rec, "type", "snmptrap"),
        _chk_literal(rec, "metric_name", "ServiceWatch"),
        _chk_sev_in(rec, ("1",), "iMark_AWSは常に重大(1)"),
        _chk_nonempty(rec, "node", "ノード"),
        _chk_nonempty(rec, "message_key", "メッセージキー"),
        _chk_nonempty(rec, "description", "説明"),
        _chk_type_big(rec, "AWS"),
    ]


def validate_imark_sv(rec: dict) -> list:
    """Trap 119 + OID .300.0/.300.1 → iMark_SV ルール処理後アラート。"""
    return [
        _chk_literal(rec, "source", "iMark_SV"),
        _chk_literal(rec, "type", "snmptrap"),
        _chk_literal(rec, "metric_name", "ServiceWatch"),
        _chk_sev_in(rec, ("1", "2", "3", "4"), "iMark_SVは重大(1)/重要(2)/マイナー(3)/警告(4)"),
        _chk_nonempty(rec, "node", "ノード"),
        _chk_nonempty(rec, "message_key", "メッセージキー"),
        _chk_nonempty(rec, "description", "説明"),
        _chk_type_big(rec, "SV"),
    ]


def validate_hw_dell(rec: dict) -> list:
    """Trap 674 (Dell iDRAC) ルール処理後アラート。"""
    return [
        _chk_literal(rec, "source", "HW監視"),
        _chk_literal(rec, "type", "snmptrap"),
        _chk_literal(rec, "resource", "Dell iDRAC"),
        _chk_sev_in(rec, ("3", "4", "5"), "Trap674はマイナー(3)/警告(4)/情報(5)"),
        _chk_nonempty(rec, "node", "ノード"),
        _chk_nonempty(rec, "message_key", "メッセージキー"),
        _chk_type_big(rec, "SV"),
    ]


def validate_hw_bigip(rec: dict) -> list:
    """Trap 3375 (BIG-IP) ルール処理後アラート。"""
    return [
        _chk_literal(rec, "source", "HW監視"),
        _chk_literal(rec, "type", "snmptrap"),
        _chk_literal(rec, "resource", "BIG-IP"),
        _chk_sev_in(rec, ("3",), "Trap3375はマイナー(3)"),
        _chk_nonempty(rec, "message_key", "メッセージキー"),
        _chk_type_big(rec, "SV"),
    ]


def validate_hw_a10(rec: dict) -> list:
    """Trap 22610 (A10) ルール処理後アラート。"""
    return [
        _chk_literal(rec, "source", "HW監視"),
        _chk_literal(rec, "type", "snmptrap"),
        _chk_literal(rec, "resource", "A10"),
        _chk_sev_in(rec, ("3", "4"), "Trap22610はマイナー(3)または警告(4)"),
        _chk_nonempty(rec, "node", "ノード"),
        _chk_nonempty(rec, "message_key", "メッセージキー"),
        _chk_type_big(rec, "SV"),
    ]


def _passthrough_base(rec: dict, source_val: str, type_big: str,
                      required: list, sev_allowed: tuple, sev_note: str,
                      warn_maxlen_fields: frozenset = frozenset()) -> list:
    """イベントフィールドをパススルーするルール共通バリデーター。"""
    r = [_chk_literal(rec, "source", source_val)]
    for fname, label in required:
        r.append(_chk_nonempty(rec, fname, label))
    r.append(_chk_sev_in(rec, sev_allowed, sev_note))
    r.append(_chk_type_big(rec, type_big))
    r += _chk_maxlen_list(rec, warn_maxlen_fields)
    return r


def validate_cloudwatch(rec: dict) -> list:
    # type は仕様上 CloudWatchLogs では未使用（spec: "-"）
    r = _passthrough_base(
        rec, "CloudWatchLogs", "AWS",
        [("node", "ノード"), ("resource", "リソース"),
         ("message_key", "メッセージキー"), ("description", "説明"),
         ("additional_info", "追加情報")],
        ("1", "2", "3", "4", "5"),
        "ALARM+critical→重大(1), ALARM+warn→重要(2), INSUFFICIENT_DATA→マイナー(3), OK→情報(5), 警告(4)も許容",
    )
    extra = _chk_metric_name_expanded(rec)
    if extra:
        r.append(extra)
    return r


def validate_cloudwatch_hios(rec: dict) -> list:
    return _passthrough_base(
        rec, "CloudWatchLogs(HIOS)", "AWS",
        [("node", "ノード"), ("resource", "リソース"),
         ("message_key", "メッセージキー"), ("description", "説明"),
         ("additional_info", "追加情報")],
        ("1", "2", "3", "4", "5"),
        "ALARM+critical→重大(1), ALARM+warn→重要(2), INSUFFICIENT_DATA→マイナー(3), OK→情報(5), 警告(4)も許容",
    )


def validate_hios_aws(rec: dict) -> list:
    return _passthrough_base(
        rec, "HIOS(AWS)", "AWS",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明")],
        ("2", "4"), "重要(2) または 警告(4)（サーバリブートは警告(4)）",
    )


def validate_hios_sv(rec: dict) -> list:
    return _passthrough_base(
        rec, "HIOS(SV)", "SV",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明")],
        ("2", "3", "4", "5"),
        "危険/重要警戒域→重要(2), 警戒/注意域→マイナー(3), 警告(4)も許容, 正常域→情報(5)",
    )


def validate_rds(rec: dict) -> list:
    return _passthrough_base(
        rec, "RDS", "AWS",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"),
         ("additional_info", "追加情報")],
        ("1", "2", "3", "5"),
        "shutdown/failover→重大(1), 復旧→情報(5), その他→重要(2), マイナー(3)も許容",
    )


def validate_nnmi(rec: dict) -> list:
    return _passthrough_base(
        rec, "NNMi", "SV",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明")],
        ("2", "5"),
        "HighImpact→重要(2), NoImpact→情報(5)",
    )


def validate_syslog(rec: dict) -> list:
    return _passthrough_base(
        rec, "syslog", "NW",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明")],
        ("1", "2"),
        "direction:syslog→重大(1), criticalから始まる件名→重要(2)",
    )


def validate_dead_letter_queue(rec: dict) -> list:
    return _passthrough_base(
        rec, "Dead Letter Queue", "AWS",
        [("message_key", "メッセージキー"), ("description", "説明"),
         ("additional_info", "追加情報")],
        ("2", "5"),
        "ALARM→重要(2), OK→情報(5)",
    )


def validate_zabbix(rec: dict) -> list:
    # Zabbix の additional_info は event 情報を多数含み 4000文字超えが想定される仕様のため WARN 扱い
    r = _passthrough_base(
        rec, "Zabbix", "NW",
        [("node", "ノード"), ("metric_name", "メトリクス名"),
         ("event_class", "ソースインスタンス"), ("message_key", "メッセージキー"),
         ("description", "説明")],
        ("0", "1", "2", "3", "4", "5"),
        "Zabbix優先度: 5→重大(1), 4→重要(2), 3→マイナー(3), 2→警告(4), 1/0→情報(5), 復旧→クリア(0)",
        warn_maxlen_fields=frozenset({"additional_info"}),
    )
    ec = _get_str(rec, "event_class")
    if ec and "Zabbix" not in ec:
        r.append(CheckResult("event_class", "NG", "'Zabbix'を含む", ec[:80],
                             "ソースインスタンスは 'Zabbix 本番' 等の形式のはず"))
    return r


def validate_prtg(rec: dict) -> list:
    # 仕様書: resource=None、metric=None（イベントルールで出力しない）
    return _passthrough_base(
        rec, "PRTG", "SV",
        [("node", "ノード"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"),
         ("additional_info", "追加情報")],
        ("1", "2", "4", "5"),
        "Down→重大(1), DownPartial→重要(2), Paused/Unknown/Warning→警告(4), Up/Active→情報(5)",
    )


def validate_carrier_hikari(rec: dict) -> list:
    return _passthrough_base(
        rec, "キャリア障害(光回線)", "その他",
        [("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_carrier_gas(rec: dict) -> list:
    return _passthrough_base(
        rec, "キャリア障害(GASフィルター後)", "その他",
        [("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_carrier_type_a(rec: dict) -> list:
    return _passthrough_base(
        rec, "キャリア障害(type A)", "その他",
        [("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_triple_error(rec: dict) -> list:
    return _passthrough_base(
        rec, "Triplエラー", "NW",
        [("event_class", "ソースインスタンス"), ("message_key", "メッセージキー"),
         ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_downdetector(rec: dict) -> list:
    # node/type は旧フォーマットでは空の場合があるため必須チェック対象外
    return _passthrough_base(
        rec, "Downdetector", "その他",
        [("resource", "リソース"), ("event_class", "ソースインスタンス"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        ("3", "4"), "マイナー(3) または 警告(4)",
    )


def validate_jpix(rec: dict) -> list:
    return _passthrough_base(
        rec, "JPIX", "NW",
        [("event_class", "ソースインスタンス"), ("message_key", "メッセージキー"),
         ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_weathernews(rec: dict) -> list:
    return _passthrough_base(
        rec, "ウェザーニューズ", "その他",
        [("event_class", "ソースインスタンス"), ("message_key", "メッセージキー"),
         ("description", "説明"), ("additional_info", "追加情報")],
        ("3",), "マイナー(3)固定",
    )


def validate_em_self_monitoring(rec: dict) -> list:
    return _passthrough_base(
        rec, "EMSelfMonitoring", "その他",
        [("type", "タイプ"), ("resource", "リソース"), ("metric_name", "メトリクス名"),
         ("message_key", "メッセージキー"), ("description", "説明"), ("additional_info", "追加情報")],
        ("1", "2", "3", "4", "5"), "重大(1)/重要(2)/マイナー(3)/警告(4)/情報(5)",
    )


def validate_direct_alert(rec: dict) -> list:
    """メール取り込み・外部API等による em_alert 直接生成ソース。em_event を経由しないためフィールド仕様なし。"""
    return []


# ---------------------------------------------------------------------------
# ソース識別テーブル
# ---------------------------------------------------------------------------

# (source値 or (source値, resource値)) → (source_type表示名, validator関数)
_SOURCE_TABLE = {
    "CloudWatchLogs":        ("CloudWatchLogs",       validate_cloudwatch),
    "CloudWatchLogs(HIOS)":  ("CloudWatchLogs(HIOS)", validate_cloudwatch_hios),
    "HIOS(AWS)":             ("HIOS(AWS)",             validate_hios_aws),
    "HIOS(SV)":              ("HIOS(SV)",              validate_hios_sv),
    "RDS":                   ("RDS",                   validate_rds),
    "NNMi":                  ("NNMi",                  validate_nnmi),
    "syslog":                ("syslog",                validate_syslog),
    "Dead Letter Queue":     ("Dead Letter Queue",     validate_dead_letter_queue),
    "Zabbix":                ("Zabbix",                validate_zabbix),
    "PRTG":                  ("PRTG",                  validate_prtg),
    "iMark_AWS":             ("iMark_AWS (Trap119)",   validate_imark_aws),
    "iMark_SV":              ("iMark_SV (Trap119)",    validate_imark_sv),
    "キャリア障害(光回線)":        ("キャリア障害(光回線)",        validate_carrier_hikari),
    "キャリア障害(GASフィルター後)": ("キャリア障害(GASフィルター後)", validate_carrier_gas),
    "キャリア障害(type A)":      ("キャリア障害(type A)",      validate_carrier_type_a),
    "Triplエラー":              ("Triplエラー",              validate_triple_error),
    "Downdetector":            ("Downdetector",            validate_downdetector),
    "JPIX":                    ("JPIX",                    validate_jpix),
    "ウェザーニューズ":            ("ウェザーニューズ",            validate_weathernews),
    "EMSelfMonitoring":        ("EMSelfMonitoring",        validate_em_self_monitoring),
    # --- メール取り込み・外部API等による em_alert 直接生成ソース ---
    "業連メール":                       ("メールからAlertへの変換", validate_direct_alert),
    "DDoS":                            ("メールからAlertへの変換", validate_direct_alert),
    "Mackerel":                        ("メールからAlertへの変換", validate_direct_alert),
    "Group Alert":                     ("メールからAlertへの変換", validate_direct_alert),
    "WebAI":                           ("メールからAlertへの変換", validate_direct_alert),
    "Service Health Dashboard Alarm":  ("メールからAlertへの変換", validate_direct_alert),
    "Email":                           ("メールからAlertへの変換", validate_direct_alert),
    "キャリア障害(type D)":              ("メールからAlertへの変換", validate_direct_alert),
    "DeepField/Arbor vSP":             ("メールからAlertへの変換", validate_direct_alert),
    "ServiceNowテストメールアラート":     ("メールからAlertへの変換", validate_direct_alert),
    "ExpressList表示対象外":             ("メールからAlertへの変換", validate_direct_alert),
    "SNMPv1 Generic Trap":             ("メールからAlertへの変換", validate_direct_alert),
    "工事連絡":                          ("メールからAlertへの変換", validate_direct_alert),
    "bousai":                          ("メールからAlertへの変換", validate_direct_alert),
    "ServiceNow UATテストメールアラート": ("メールからAlertへの変換", validate_direct_alert),
    "AWS maintenance":                 ("メールからAlertへの変換", validate_direct_alert),
    "SNMPv2 Generic Trap":             ("メールからAlertへの変換", validate_direct_alert),
}

# HW監視系は source=HW監視 + resource で区別
_HW_RESOURCE_TABLE = {
    "Dell iDRAC": ("HW監視 (Trap674/Dell iDRAC)", validate_hw_dell),
    "BIG-IP":     ("HW監視 (Trap3375/BIG-IP)",    validate_hw_bigip),
    "A10":        ("HW監視 (Trap22610/A10)",       validate_hw_a10),
}


def identify_source(rec: dict) -> tuple[str, object]:
    """(source_type表示名, validator関数) を返す。不明な場合は (UNKNOWN, None)。"""
    src = _get_str(rec, "source")
    res = _get_str(rec, "resource")

    if not src:
        return ("メールからAlertへの変換", validate_direct_alert)

    if src == "HW監視":
        if res in _HW_RESOURCE_TABLE:
            return _HW_RESOURCE_TABLE[res]
        return (f"HW監視 (resource={res!r} 未定義)", None)

    entry = _SOURCE_TABLE.get(src)
    if entry:
        return entry

    return ("UNKNOWN", None)


def validate_alert(rec: dict) -> AlertResult:
    src = _get_str(rec, "source")
    sys_id = _get_str(rec, "sys_id")
    source_type, validator = identify_source(rec)

    if validator is None:
        return AlertResult(
            sys_id=sys_id, source=src, source_type=source_type,
            status="UNKNOWN_SOURCE",
            checks=[CheckResult("source", "NG", "既知のソース値", src,
                                f"未定義ソース: {src!r}")]
        )

    checks = validator(rec)
    has_ng = any(c.status == "NG" for c in checks)
    return AlertResult(
        sys_id=sys_id, source=src, source_type=source_type,
        status="NG" if has_ng else "OK",
        checks=checks,
    )
