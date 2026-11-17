"""Командная строка: список ников и проверка.

Список берётся из маски (masks.py) или из своего файла.
Проверка одного ника живёт в probe.py и от перебора не зависит.

    python check.py --expand zovXX
    python check.py --http zovXX zovXXX
    python check.py --http --names names.txt
    python check.py --mt --names names.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import masks
import probe

ROOT = Path(__file__).resolve().parent


def read_names(path: Path) -> list[str]:
    """Файл своего перебора: один ник на строку. Пустые строки и хвост после # пропускаются."""
    names: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = probe.normalize(line)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def split_local(names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    ready: list[str] = []
    rows: list[tuple[str, str]] = []
    for name in names:
        issue = probe.local_issue(name)
        if issue:
            print(f"{name}\tinvalid\t{issue}", file=sys.stderr)
            rows.append((name, "invalid"))
        else:
            ready.append(name)
    return ready, rows


def http_scan(names: list[str], workers: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe.http_status, name): name for name in names}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                status = fut.result()
            except Exception as exc:
                status = f"error {type(exc).__name__}"
            rows.append((name, status))
            done += 1
            if done % 50 == 0 or done == len(names):
                print(f"http {done}/{len(names)}", file=sys.stderr, flush=True)
    return rows


async def mt_scan(names: list[str], delay: float) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    async with probe.UsernameSession() as checker:
        for index, name in enumerate(names, start=1):
            status = await checker.check(name)
            rows.append((name, status))
            if index % 25 == 0 or index == len(names):
                print(f"mt {index}/{len(names)} {name} {status}", file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
    return rows


def write_rows(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows)
    lines = [f"{name}\t{status}" for name, status in ordered]
    counts: dict[str, int] = {}
    for _, status in ordered:
        key = status if status in probe.STATUSES else "error"
        counts[key] = counts.get(key, 0) + 1
    summary = " ".join(f"{key}={counts.get(key, 0)}" for key in probe.STATUSES)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary, file=sys.stderr)
    print(path, file=sys.stderr)


def main() -> None:
    probe.load_env()
    parser = argparse.ArgumentParser(
        description="Проверка ников Telegram. Маска с X — готовый перебор цифр. Свой список — --names."
    )
    parser.add_argument("masks", nargs="*", help="например zovXX zovXXX; X — цифра")
    parser.add_argument("--names", type=Path, help="свой список, один ник на строку")
    parser.add_argument("--login", action="store_true", help="один раз войти и сохранить сессию")
    parser.add_argument("--expand", action="store_true", help="только раскрыть маску, без запросов")
    parser.add_argument("--http", action="store_true", help="только t.me и Fragment, без вердикта free")
    parser.add_argument("--mt", action="store_true", help="account.checkUsername по каждому нику")
    parser.add_argument("-o", "--output", type=Path, help="tsv с результатом")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.4, help="пауза между запросами checkUsername")
    parser.add_argument("--limit", type=int, default=20000)
    args = parser.parse_args()

    if args.login:
        asyncio.run(probe.login())
        return

    if args.names and args.masks:
        parser.error("нужно что-то одно: маски или --names")
    if not args.names and not args.masks:
        parser.error("нужна маска, например zovXX, или --names файл")
    if args.expand and args.names:
        parser.error("--expand раскрывает маску; свой список уже готов")

    if args.names:
        if not args.names.is_file():
            parser.error(f"нет файла {args.names}")
        names = read_names(args.names)
        if not names:
            parser.error("в файле нет ников")
        label = args.names.stem
    else:
        try:
            names = masks.expand_masks(args.masks, args.limit)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        label = "-".join(args.masks).lower()

    if args.expand:
        print("\n".join(names))
        print(f"{len(names)} ников", file=sys.stderr)
        return

    ready, rows = split_local(names)
    use_mt = args.mt or (not args.http and probe.SESSION.is_file() and os.environ.get("TG_API_ID"))
    if use_mt:
        if ready:
            rows.extend(asyncio.run(mt_scan(ready, args.delay)))
    else:
        if not args.http:
            print(
                "Сессии нет: проверяю только публичные страницы. "
                "unknown значит «карточки и лота нет», не «ник свободен». "
                "Ответ как в поле настроек даёт только --mt.",
                file=sys.stderr,
            )
        if ready:
            rows.extend(http_scan(ready, args.workers))

    output = args.output
    if output is None:
        output = ROOT / "out" / f"{label}.tsv"
    write_rows(output, rows)


if __name__ == "__main__":
    main()
