"""Проверка одного ника Telegram.

Перебор сюда не входит. Список имён собирает вызывающий код:
маска из masks.py, свой генератор, файл.

Без сессии доступна только публичная проверка. Она читает t.me и Fragment
и не возвращает free: пустая страница одинакова у свободного ника,
у занятого без карточки и у удержанного.

account.checkUsername — тот же ответ, что у поля в настройках.
Ему нужна своя сессия.

    from probe import check_public, check_username

    check_public("zov77")
    await check_username(client, "zov77")
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "tg.session"
UA = {"User-Agent": "tg-username-search"}

STATUSES = ("free", "reserved", "sale", "taken", "unknown", "invalid", "error")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env(path: Path | None = None) -> None:
    path = ROOT / ".env" if path is None else path
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize(name: str) -> str:
    return name.strip().lower()


def local_issue(name: str) -> str | None:
    """Правила символов. None — форма ника допустима, это ещё не значит, что он свободен."""
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
    """t.me и Fragment для одного ника. free отсюда не возвращается."""
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
                return "unknown"
            return "error"
        except Exception as exc:
            last_error = f"error {type(exc).__name__}"
            time.sleep(1.2 * (attempt + 1))
    return last_error


def check_public(name: str) -> str:
    """Публичная проверка одного ника. Свой список передают по одному имени."""
    name = normalize(name)
    if local_issue(name):
        return "invalid"
    return http_status(name)


async def check_username(client, name: str) -> str:
    """account.checkUsername через уже подключённый TelegramClient."""
    from telethon.errors import (
        FloodWaitError,
        UsernameInvalidError,
        UsernameOccupiedError,
        UsernamePurchaseAvailableError,
    )
    from telethon.tl.functions.account import CheckUsernameRequest

    name = normalize(name)
    if local_issue(name):
        return "invalid"
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


def _credentials() -> tuple[int, str]:
    load_env()
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit("Нет TG_API_ID / TG_API_HASH. Скопируй .env.example в .env и заполни с my.telegram.org.")
    return int(api_id), api_hash


class UsernameSession:
    """Сессия для пачки своих ников. Чужой клиент Telethon сюда не нужен: его передают в check_username."""

    def __init__(self, session: Path | None = None) -> None:
        self.session = SESSION if session is None else session
        self.client = None

    async def __aenter__(self) -> "UsernameSession":
        from telethon import TelegramClient

        api_id, api_hash = _credentials()
        if not self.session.is_file():
            raise SystemExit("Нет сессии. Сначала: python check.py --login")
        self.client = TelegramClient(str(self.session), api_id, api_hash)
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise SystemExit("Сессия не авторизована. Сначала: python check.py --login")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.client is not None:
            await self.client.disconnect()

    async def check(self, name: str) -> str:
        return await check_username(self.client, name)


async def login(session: Path | None = None) -> None:
    from telethon import TelegramClient

    api_id, api_hash = _credentials()
    path = SESSION if session is None else session
    client = TelegramClient(str(path), api_id, api_hash)
    await client.start()
    me = await client.get_me()
    print(f"вошли как {me.username or me.id}", file=sys.stderr)
    await client.disconnect()
