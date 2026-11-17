"""Проверка ников Telegram по маске.

В маске заглавная X — цифра 0–9. Остальные символы буквальные.
zovXX даёт zov00…zov99, zovXXX даёт zov000…zov999.

Без входа в аккаунт скрипт читает только t.me и Fragment. Пустая страница
t.me одинакова у свободного ника, у занятого без карточки и у удержанного.
Такой результат называется unknown. Свободным ник бывает только после
account.checkUsername.

С сессией вызывается account.checkUsername — тот же ответ, что у поля
в настройках.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "tg.session"
UA = {"User-Agent": "tg-username-masks"}

STATUSES = ("free", "reserved", "sale", "taken", "unknown", "invalid", "error")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def local_issue(name: str) -> str | None:
    if not 5 <= len(name) <= 32:
        return "длина не 5–32"
    if not re.fullmatch(r"[a-z][a-z0-9_]{3,30}[a-z0-9]", name):
        return "не подходит под правило символов"
    if "__" in name:
        return "два подчёркивания подряд"
    return None


def fetch(url: str) -> tuple[int, str]:
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers=UA)
    try:
        with opener.open(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body


def fragment_state(code: int, html: str) -> str:
    if code in (301, 302, 303, 307, 308):
        return "none"
    if code != 200:
        return f"http {code}"
    match = re.search(r"tm-section-header-status[^>]*>(.*?)<", html, re.S)
    text = re.sub(r"\s+", " ", match.group(1)).strip().lower() if match else ""
    if "taken" in text:
        return "taken"
    if text in ("available", "for sale", "on auction") or "sale" in text or "auction" in text:
        return "sale"
    if "sold" in text:
        return "sold"
    return "unknown"


def http_status(name: str) -> str:
    last_error = "error"
    for attempt in range(4):
        try:
            t_code, t_html = fetch(f"https://t.me/{name}")
            f_code, f_html = fetch(f"https://fragment.com/username/{name}")
            if t_code != 200:
                raise RuntimeError(f"t.me {t_code}")
            profile = "tgme_page_extra" in t_html
            frag = fragment_state(f_code, f_html)
            if profile or frag in ("taken", "sold"):
                return "taken"
            if frag == "sale":
                return "sale"
            if frag == "none":
                # Та же вёрстка у свободного, занятого без карточки и удержанного.
                return "unknown"
            return "error"
        except Exception as exc:
            last_error = f"error {type(exc).__name__}"
            time.sleep(1.2 * (attempt + 1))
    return last_error


def http_scan(names: list[str], workers: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(http_status, name): name for name in names}
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
    rows.sort()
    return rows


async def mt_one(client, name: str) -> str:
    from telethon.errors import (
        FloodWaitError,
        UsernameInvalidError,
        UsernameOccupiedError,
        UsernamePurchaseAvailableError,
    )
    from telethon.tl.functions.account import CheckUsernameRequest

    for _ in range(5):
        try:
            ok = await client(CheckUsernameRequest(name))
            return "free" if ok else "taken"
        except UsernameOccupiedError:
            return "taken"
        except UsernamePurchaseAvailableError:
            return "sale"
        except UsernameInvalidError:
            return "reserved"
        except FloodWaitError as exc:
            print(f"flood wait {exc.seconds}s", file=sys.stderr, flush=True)
            await _asleep(exc.seconds + 1)
    return "error"


async def _asleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def mt_scan(names: list[str], delay: float) -> list[tuple[str, str]]:
    import asyncio

    from telethon import TelegramClient

    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit("Нет TG_API_ID / TG_API_HASH. Скопируй .env.example в .env и заполни с my.telegram.org.")
    if not SESSION.is_file():
        raise SystemExit("Нет сессии. Сначала: python check.py --login")

    client = TelegramClient(str(SESSION), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Сессия не авторизована. Сначала: python check.py --login")

    rows: list[tuple[str, str]] = []
    try:
        for index, name in enumerate(names, start=1):
            if local_issue(name):
                status = "invalid"
            else:
                status = await mt_one(client, name)
            rows.append((name, status))
            if index % 25 == 0 or index == len(names):
                print(f"mt {index}/{len(names)} {name} {status}", file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
    finally:
        await client.disconnect()
    return rows


async def login() -> None:
    from telethon import TelegramClient

    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit("Нет TG_API_ID / TG_API_HASH в окружении или в .env.")
    client = TelegramClient(str(SESSION), int(api_id), api_hash)
    await client.start()
    me = await client.get_me()
    print(f"вошли как {me.username or me.id}", file=sys.stderr)
    await client.disconnect()


def write_rows(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}\t{status}" for name, status in rows]
    counts: dict[str, int] = {}
    for _, status in rows:
        key = status if status in STATUSES else "error"
        counts[key] = counts.get(key, 0) + 1
    summary = " ".join(f"{key}={counts.get(key, 0)}" for key in STATUSES)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary, file=sys.stderr)
    print(path, file=sys.stderr)


def names_from_masks(masks: list[str], limit: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for mask in masks:
        for name in expand_mask(mask):
            if name in seen:
                continue
            seen.add(name)
            issue = local_issue(name)
            if issue:
                print(f"{name}\tinvalid\t{issue}", file=sys.stderr)
                continue
            names.append(name)
    if len(names) > limit:
        raise SystemExit(f"Маска раскрывается в {len(names)} ников, лимит {limit}. Подними --limit, если это ожидаемо.")
    return names


def main() -> None:
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Проверка ников Telegram по маске. X — цифра.")
    parser.add_argument("masks", nargs="*", help="например zovXX zovXXX")
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
        import asyncio

        asyncio.run(login())
        return

    if not args.masks:
        parser.error("нужна маска, например zovXX")

    names = names_from_masks(args.masks, args.limit)
    if args.expand:
        print("\n".join(names))
        print(f"{len(names)} ников", file=sys.stderr)
        return

    use_mt = args.mt or (not args.http and SESSION.is_file() and os.environ.get("TG_API_ID"))
    if use_mt:
        import asyncio

        rows = asyncio.run(mt_scan(names, args.delay))
    else:
        if not args.http:
            print(
                "Сессии нет: проверяю только публичные страницы. "
                "unknown значит «карточки и лота нет», не «ник свободен». "
                "Ответ как в поле настроек даёт только --mt.",
                file=sys.stderr,
            )
        rows = http_scan(names, args.workers)

    output = args.output
    if output is None:
        slug = "-".join(args.masks).lower()
        output = ROOT / "out" / f"{slug}.tsv"
    write_rows(output, rows)


if __name__ == "__main__":
    main()
