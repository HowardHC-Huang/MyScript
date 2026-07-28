"""Excel 中 expect_type=custom 時，由此模組解析 expect_value 名稱。"""

import re
from datetime import datetime
from typing import Callable, Dict, Optional

from at_core import TTFF_MAX_SEC, TTFF_PATTERN, parse_ttff_sec

ExpectFn = Callable[[str], bool]


def _expect_current_year_month(response: str) -> bool:
    now = datetime.now()
    label = f"{now.year} {now.month:02d}"
    return label in response


def _make_expect_gps_status(max_sec: float) -> ExpectFn:
    def check(response: str) -> bool:
        if "OK" not in response:
            return False
        ttff = parse_ttff_sec(response)
        if ttff is None:
            return False
        return ttff < max_sec

    return check


def _label_current_year_month() -> str:
    now = datetime.now()
    return f"{now.year} {now.month:02d}"


def _label_gps_status(max_sec: float) -> str:
    return f"TTFF (sec) < {max_sec}"


# expect_value（或別名）→ (checker, label_factory)
# label_factory 可為 None，表示用 expect_value 當 label
CUSTOM_REGISTRY: Dict[str, tuple] = {
    "current_year_month": (_expect_current_year_month, _label_current_year_month),
    "gps_status_ttff": (
        _make_expect_gps_status(TTFF_MAX_SEC),
        lambda: _label_gps_status(TTFF_MAX_SEC),
    ),
}


def resolve_custom_expect(expect_value: str) -> tuple:
    """
    解析 custom expect_value。
    支援：
      - current_year_month
      - gps_status_ttff
      - gps_status_ttff:5  （自訂 TTFF 門檻秒數）
    回傳 (callable, label_str)。
    """
    value = (expect_value or "").strip()
    if not value:
        raise ValueError("expect_type=custom 時 expect_value 不可為空")

    if value in CUSTOM_REGISTRY:
        checker, label_fn = CUSTOM_REGISTRY[value]
        return checker, label_fn()

    match = re.fullmatch(r"gps_status_ttff:(\d+(?:\.\d+)?)", value, re.IGNORECASE)
    if match:
        max_sec = float(match.group(1))
        return _make_expect_gps_status(max_sec), _label_gps_status(max_sec)

    known = ", ".join(sorted(CUSTOM_REGISTRY.keys()))
    raise ValueError(
        f"未知的 custom expect_value: {value!r}（可用: {known}, gps_status_ttff:<秒數>）"
    )
