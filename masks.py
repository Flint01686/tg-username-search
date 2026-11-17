"""Раскрытие маски в список ников.

Это один готовый перебор, не часть проверки. Заглавная X — цифра 0–9.
Остальные символы буквальные и приводятся к нижнему регистру.
zovXX даёт zov00…zov99, zovXXX даёт zov000…zov999.

Свой алфавит, словарь или другой перебор сюда не добавляют:
имена пишут в файл и передают в check.py --names
или по одному в probe.check_public / probe.check_username.
"""

from __future__ import annotations


def expand_mask(mask: str) -> list[str]:
    """Заглавная X — слот цифры. Остальное копируется как есть, в нижнем регистре."""
    if not mask or any(ch.isspace() for ch in mask):
        raise ValueError(f"пустая или с пробелом маска: {mask!r}")
    alphabet = "0123456789"
    slots = [alphabet if ch == "X" else ch.lower() for ch in mask]
    names = [""]
    for slot in slots:
        names = [prefix + ch for prefix in names for ch in slot]
    return names


def expand_masks(masks: list[str], limit: int = 20000) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for mask in masks:
        for name in expand_mask(mask):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    if len(names) > limit:
        raise ValueError(f"Маска раскрывается в {len(names)} ников, лимит {limit}.")
    return names
