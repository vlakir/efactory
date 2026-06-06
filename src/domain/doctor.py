"""Doctor — domain VOs для диагностики тулчейна (T036).

`efactory doctor` собирает отчёт о состоянии тулчейна в образе:
versions внешних бинарей, доступность mount-точек, GUI passthrough,
runtime-лимиты. Domain-уровень — без знания о subprocess / FS.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class CheckStatus(str, Enum):
    """Статус единичной проверки. Сортировка по `.severity`."""

    OK = 'OK'
    WARN = 'WARN'
    FAIL = 'FAIL'

    @property
    def severity(self) -> int:
        return _SEVERITY[self]


_SEVERITY = {
    CheckStatus.OK: 0,
    CheckStatus.WARN: 1,
    CheckStatus.FAIL: 2,
}


CATEGORY_TOOLCHAIN = 'toolchain'
CATEGORY_GUI = 'gui'
CATEGORY_MOUNTS = 'mounts'
CATEGORY_RUNTIME = 'runtime'
CATEGORY_HOST = 'host'

CANONICAL_CATEGORY_ORDER: tuple[str, ...] = (
    CATEGORY_TOOLCHAIN,
    CATEGORY_GUI,
    CATEGORY_MOUNTS,
    CATEGORY_RUNTIME,
    CATEGORY_HOST,
)


class DoctorCheck(BaseModel):
    """Результат одной диагностической проверки."""

    model_config = _FROZEN

    name: str = Field(min_length=1)
    status: CheckStatus
    detail: str
    category: str = Field(min_length=1)


class DoctorReport(BaseModel):
    """Сводный отчёт `efactory doctor`."""

    model_config = _FROZEN

    checks: tuple[DoctorCheck, ...]

    @property
    def worst_status(self) -> CheckStatus:
        if not self.checks:
            return CheckStatus.OK
        return max(self.checks, key=lambda c: c.status.severity).status

    def iter_categories(
        self,
    ) -> list[tuple[str, tuple[DoctorCheck, ...]]]:
        """Группировка по категориям. Canonical-категории первыми, прочие — по
        первому появлению."""
        groups: dict[str, list[DoctorCheck]] = {}
        for check in self.checks:
            groups.setdefault(check.category, []).append(check)

        ordered_keys: list[str] = []
        for canonical in CANONICAL_CATEGORY_ORDER:
            if canonical in groups:
                ordered_keys.append(canonical)
        for key in groups:
            if key not in ordered_keys:
                ordered_keys.append(key)

        return [(key, tuple(groups[key])) for key in ordered_keys]


__all__ = [
    'CANONICAL_CATEGORY_ORDER',
    'CATEGORY_GUI',
    'CATEGORY_HOST',
    'CATEGORY_MOUNTS',
    'CATEGORY_RUNTIME',
    'CATEGORY_TOOLCHAIN',
    'CheckStatus',
    'DoctorCheck',
    'DoctorReport',
]
