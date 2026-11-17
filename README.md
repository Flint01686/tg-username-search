<p align="center">
  <strong>Русский</strong> · <a href="README.en.md">English</a>
</p>

# Telegram username search

Проверка ника Telegram и отдельно от неё перебор. Проверка одного имени живёт в `probe.py`. Готовая маска, где заглавная `X` — цифра (`fsbXXX` даёт `fsb000`…`fsb999`), живёт в `masks.py`. Свой список — буквы, словарь, любой другой перебор — передаётся файлом и в маску не зашит.

Автор: [@fsb018](https://t.me/fsb018)

![Клиент пишет «Некорректное имя пользователя» для ника fsb420](docs/fsb420-invalid.png)

## Что скрипт умеет

Без входа он открывает две публичные страницы.

- `https://t.me/ник` — карточка есть, только если в HTML есть `tgme_page_extra`.
- `https://fragment.com/username/ник` — лот на продаже или его нет.

Пустая страница не значит, что ник свободен. У `fso222`, `fso888` и `zov000` вёрстка такая же, как у случайного имени, а в клиенте написано «имя пользователя уже занято». Поэтому режим `--http` ставит `unknown`, а не `free`.

Совпадает с полем «Имя пользователя» только метод [`account.checkUsername`](https://core.telegram.org/method/account.checkUsername). Это режим `--mt`, ему нужен свой вход. Сессия в репозиторий не входит.

| В приложении | Ответ | Статус скрипта |
| --- | --- | --- |
| можно сохранить | `true` | `free` |
| имя пользователя уже занято | `USERNAME_OCCUPIED` | `taken` |
| выставлена на продажу | `USERNAME_PURCHASE_AVAILABLE` | `sale` |
| некорректное имя пользователя | `USERNAME_INVALID` | `reserved` |

`USERNAME_INVALID` приходит и на формально правильный ник. Так было с `fsb420` и `fsb555`: страницы пустые, клиент имя не берёт. `fsb999` при пустой странице `t.me` уже продавался на Fragment.

## Запуск

Маска:

```text
python check.py --expand zovXX
python check.py --http zovXX zovXXX
python check.py --mt zovXX zovXXX
```

`zovXX` — `zov00`…`zov99`. `zovXXX` — `zov000`…`zov999`.

Свой список, один ник на строку:

```text
python check.py --http --names names.txt
python check.py --mt --names names.txt
```

Из своего кода, без маски и без командной строки:

```python
from probe import check_public, check_username

check_public("zov77")
await check_username(client, "zov77")
```

`client` — уже подключённый `TelegramClient`. `check_public` не возвращает `free`. Если сессия этого репозитория уже есть, пачку своих ников можно прогнать так:

```python
from probe import UsernameSession

async with UsernameSession() as checker:
    status = await checker.check("zov77")
```

Ключи и `.env` описаны в [гайде](docs/api-credentials.md). С российского адреса форма на [my.telegram.org](https://my.telegram.org) часто отвечает `Too many attempts`, и VPN эту строку не снимает. Код входа в прогоне этого репозитория до конца не дошёл: Telegram отдавал его только в приложение, без SMS и без почты.

Между запросами `--mt` пауза `--delay` (по умолчанию 0.4 с). На `FLOOD_WAIT` скрипт ждёт столько, сколько сказал сервер.

Статусы в tsv:

- `free` — `checkUsername` разрешил занять
- `taken` — уже занят
- `sale` — только покупка на Fragment
- `reserved` — `USERNAME_INVALID` при нормальной форме
- `unknown` — режим `--http`: карточки и лота нет, занят ник или нет, страница не показывает
- `invalid` — не проходит правило символов
- `error` — запрос не удался

Без `--mt` скрипт не называет ник свободным.
