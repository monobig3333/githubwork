"""
ServiceNow CI バインディングルール / フィールドマッピングルールの検証ロジック。

このインスタンスの実テーブル構成:
  sa_event_rule     : イベントルール（CIバインディング・フィールドマッピング等）← 主要
  em_rule_xml       : matchRule (CIバインディング) / fieldMappingRule (フィールドマッピング)
  em_mapping_rule   : フィールドマッピングルール
  em_binding_device_map: CI タイプ間マッピング
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    field: str
    status: str    # "OK" / "NG" / "WARN"
    expected: str
    actual: str
    message: str = ""


@dataclass
class RuleResult:
    sys_id: str
    name: str
    table: str     # "em_rule_xml(matchRule)" / "em_rule_xml(fieldMappingRule)" / "em_mapping_rule"
    status: str    # "OK" / "NG" / "WARN"
    checks: list = field(default_factory=list)

    @property
    def ng_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "NG")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _gs(rec: dict, fname: str) -> str:
    val = rec.get(fname, "")
    if isinstance(val, dict):
        return str(val.get("display_value") or val.get("value") or "")
    return str(val or "")


def _is_active(rec: dict) -> bool:
    return _gs(rec, "active").lower() in ("true", "1", "はい", "yes")


def _xt(root, path: str, default: str = "") -> str:
    el = root.find(path)
    return el.text.strip() if el is not None and el.text else default


def _chk_nonempty(value: str, fname: str, label: str) -> CheckResult:
    if value and value not in ("null", ""):
        return CheckResult(fname, "OK", f"{label}が設定されている", value[:100])
    return CheckResult(fname, "NG", f"{label}が設定されている", "", f"{label}が空です")


# ---------------------------------------------------------------------------
# em_rule_xml / matchRule バリデーター
# ---------------------------------------------------------------------------

def validate_match_rule(parsed: dict) -> RuleResult:
    """em_rule_xml の matchRule（CIバインディング）を検証する。"""
    checks: list[CheckResult] = []

    # 必須フィールドチェック
    checks.append(_chk_nonempty(parsed.get("name", ""),    "name",    "ルール名"))
    checks.append(_chk_nonempty(parsed.get("source", ""),  "source",  "ソース(EMS)"))
    checks.append(_chk_nonempty(parsed.get("ci_type", ""), "ci_type", "CIタイプ"))

    # マッチフィールドが1件以上あるか
    mf = parsed.get("match_fields", [])
    if mf:
        checks.append(CheckResult("match_fields", "OK", "マッチフィールドあり",
                                  f"{len(mf)} 件"))
    else:
        checks.append(CheckResult("match_fields", "WARN", "マッチフィールドあり",
                                  "0 件", "マッチ条件が未設定（全イベントにマッチ）"))

    # ignore=true のルールは WARN
    if parsed.get("ignore", "false").lower() == "true":
        checks.append(CheckResult("ignore", "WARN", "false", "true",
                                  "ignoreルール（処理スキップ）"))
    else:
        checks.append(CheckResult("ignore", "OK", "false",
                                  parsed.get("ignore", "false")))

    has_ng   = any(c.status == "NG"   for c in checks)
    has_warn = any(c.status == "WARN" for c in checks)

    return RuleResult(
        sys_id=parsed.get("sys_id", ""),
        name=parsed.get("name", ""),
        table="em_rule_xml(matchRule)",
        status="NG" if has_ng else ("WARN" if has_warn else "OK"),
        checks=checks,
    )


# ---------------------------------------------------------------------------
# em_mapping_rule バリデーター
# ---------------------------------------------------------------------------

def validate_mapping_rule(rec: dict) -> RuleResult:
    """em_mapping_rule の1レコードを検証する。"""
    checks: list[CheckResult] = []

    # アクティブチェック
    active = _gs(rec, "active")
    if _is_active(rec):
        checks.append(CheckResult("active", "OK", "アクティブ", active))
    else:
        checks.append(CheckResult("active", "WARN", "アクティブ", active,
                                  "非アクティブ（無効化中）"))

    checks.append(_chk_nonempty(_gs(rec, "name"),         "name",         "ルール名"))
    checks.append(_chk_nonempty(_gs(rec, "mapping_type"), "mapping_type", "マッピングタイプ"))

    # from_field または value（定数）が必要
    from_f = _gs(rec, "from_field")
    value  = _gs(rec, "value")
    if from_f or value:
        checks.append(CheckResult("from_field/value", "OK",
                                  "変換元フィールドまたは定数値が設定されている",
                                  (from_f or value)[:80]))
    else:
        checks.append(CheckResult("from_field/value", "NG",
                                  "変換元フィールドまたは定数値が設定されている",
                                  "", "from_field / value ともに空"))

    # to_field または alert_field が必要
    to_f    = _gs(rec, "to_field")
    alert_f = _gs(rec, "alert_field")
    if to_f or alert_f:
        checks.append(CheckResult("to_field/alert_field", "OK",
                                  "変換先フィールドが設定されている",
                                  (to_f or alert_f)[:80]))
    else:
        checks.append(CheckResult("to_field/alert_field", "NG",
                                  "変換先フィールドが設定されている",
                                  "", "to_field / alert_field ともに空"))

    has_ng   = any(c.status == "NG"   for c in checks)
    has_warn = any(c.status == "WARN" for c in checks)

    return RuleResult(
        sys_id=_gs(rec, "sys_id"),
        name=_gs(rec, "name"),
        table="em_mapping_rule",
        status="NG" if has_ng else ("WARN" if has_warn else "OK"),
        checks=checks,
    )


# ---------------------------------------------------------------------------
# u_transformation_rule バリデーター
# ---------------------------------------------------------------------------

# 有効なカテゴリ値
TRANSFORMATION_CATEGORIES = frozenset({
    "アラートタイプ変換",
    "メッセージ変換",
    "ログ変換",
    "監視種別変換",
    "通常抑止フィルタ",
})


def validate_transformation_rule(rec: dict) -> RuleResult:
    """u_transformation_rule の1レコードを検証する。"""
    checks: list[CheckResult] = []

    # アクティブチェック
    active = _gs(rec, "u_active")
    if active.lower() in ("true", "1", "はい", "yes"):
        checks.append(CheckResult("u_active", "OK", "アクティブ", active))
    else:
        checks.append(CheckResult("u_active", "WARN", "アクティブ", active,
                                  "非アクティブ（無効化中）"))

    checks.append(_chk_nonempty(_gs(rec, "u_rule_name"),  "u_rule_name",  "ルール名"))
    checks.append(_chk_nonempty(_gs(rec, "u_category"),   "u_category",   "カテゴリ"))
    checks.append(_chk_nonempty(_gs(rec, "u_table_name"), "u_table_name", "対象テーブル"))

    # カテゴリ値の妥当性
    cat = _gs(rec, "u_category")
    if cat and cat not in TRANSFORMATION_CATEGORIES:
        checks.append(CheckResult("u_category", "WARN",
                                  f"既知カテゴリ ({'/'.join(sorted(TRANSFORMATION_CATEGORIES))})",
                                  cat, "未知のカテゴリ値"))

    # 条件が空の場合は全アラートに適用されるため WARN
    cond = _gs(rec, "u_conditions")
    if cond and cond not in ("null", ""):
        checks.append(CheckResult("u_conditions", "OK", "条件が設定されている", cond[:80]))
    else:
        checks.append(CheckResult("u_conditions", "WARN", "条件が設定されている",
                                  "", "条件なし（全アラートに適用）"))

    has_ng   = any(c.status == "NG"   for c in checks)
    has_warn = any(c.status == "WARN" for c in checks)

    return RuleResult(
        sys_id=_gs(rec, "sys_id"),
        name=_gs(rec, "u_rule_name"),
        table="u_transformation_rule",
        status="NG" if has_ng else ("WARN" if has_warn else "OK"),
        checks=checks,
    )


# ---------------------------------------------------------------------------
# 重複チェック
# ---------------------------------------------------------------------------

def check_duplicate_orders_mapping(results: list[RuleResult],
                                    recs: list[dict]) -> list[str]:
    """em_mapping_rule 内で order 値が重複しているルールを返す。"""
    from collections import defaultdict
    order_map: dict = defaultdict(list)
    for rec, result in zip(recs, results):
        order_val = _gs(rec, "order")
        if order_val:
            order_map[order_val].append(result.name or result.sys_id)
    return [f"order={o}: {', '.join(names)}"
            for o, names in order_map.items() if len(names) > 1]


# ---------------------------------------------------------------------------
# sa_event_rule バリデーター
# ---------------------------------------------------------------------------

# sa_event_rule の type フィールドで期待される値（標準 EM）
SA_EVENT_RULE_TYPES = frozenset({
    "binding",
    "field_mapping",
    "severity_mapping",
    "suppression",
    "alert_description",
})


def validate_sa_event_rule(rec: dict) -> "RuleResult":
    """sa_event_rule の1レコードを検証する。"""
    checks: list[CheckResult] = []

    # アクティブチェック
    active = _gs(rec, "active")
    if active.lower() in ("true", "1", "はい", "yes"):
        checks.append(CheckResult("active", "OK", "アクティブ", active))
    else:
        checks.append(CheckResult("active", "WARN", "アクティブ", active,
                                  "非アクティブ（無効化中）"))

    checks.append(_chk_nonempty(_gs(rec, "name"),  "name",  "ルール名"))
    checks.append(_chk_nonempty(_gs(rec, "type"),  "type",  "ルールタイプ"))

    # ルールタイプが既知の値か確認
    rule_type = _gs(rec, "type")
    if rule_type and rule_type not in SA_EVENT_RULE_TYPES:
        checks.append(CheckResult("type", "WARN",
                                  f"既知タイプ ({'/'.join(sorted(SA_EVENT_RULE_TYPES))})",
                                  rule_type, "未知のルールタイプ"))

    # 条件が空の場合は全イベントに適用されるため WARN
    cond = _gs(rec, "conditions")
    if cond and cond not in ("null", ""):
        checks.append(CheckResult("conditions", "OK", "条件が設定されている", cond[:80]))
    else:
        checks.append(CheckResult("conditions", "WARN", "条件が設定されている",
                                  "", "条件なし（全イベントに適用）"))

    # バインディングタイプの場合は CI クラスが必要
    if rule_type == "binding":
        ci_class = _gs(rec, "ci_class")
        if ci_class:
            checks.append(CheckResult("ci_class", "OK", "CIクラスが設定されている",
                                      ci_class[:80]))
        else:
            checks.append(CheckResult("ci_class", "WARN", "CIクラスが設定されている",
                                      "", "バインディングルールにCIクラス未設定"))

    has_ng   = any(c.status == "NG"   for c in checks)
    has_warn = any(c.status == "WARN" for c in checks)

    return RuleResult(
        sys_id=_gs(rec, "sys_id"),
        name=_gs(rec, "name"),
        table="sa_event_rule",
        status="NG" if has_ng else ("WARN" if has_warn else "OK"),
        checks=checks,
    )


def check_duplicate_orders_transformation(results: list[RuleResult],
                                           recs: list[dict]) -> list[str]:
    """u_transformation_rule 内で u_order 値が重複しているルールを返す。"""
    from collections import defaultdict
    order_map: dict = defaultdict(list)
    for rec, result in zip(recs, results):
        # カンマ区切り数値（例: "3,800"）を正規化してキーにする
        order_val = _gs(rec, "u_order").replace(",", "")
        if order_val:
            order_map[order_val].append(result.name or result.sys_id)
    return [f"order={o}: {', '.join(names)}"
            for o, names in order_map.items() if len(names) > 1]
