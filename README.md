<p align="center">
  <strong>English</strong> · <a href="README.ru.md">Русский</a>
</p>

# Telegram username search

Search Telegram usernames by mask and see what a public page can actually tell you. An uppercase `X` in the mask is a digit: `fsbXXX` expands to `fsb000`…`fsb999`.

Author: [@fsb018](https://t.me/fsb018)

![The Telegram client says the username is invalid for fsb420](docs/fsb420-invalid.png)

## What the script does

Without a login it opens two public pages.

- `https://t.me/name` shows a profile card only when the HTML contains `tgme_page_extra`.
- `https://fragment.com/username/name` shows a listing, or it does not.

An empty page does not mean the name is free. `fso222`, `fso888`, and `zov000` look like a random unused name, and the app still says the username is already taken. `--http` therefore records `unknown`, not `free`.

The settings field matches only [`account.checkUsername`](https://core.telegram.org/method/account.checkUsername). That is `--mt`, and it needs your own login. The session file stays out of the repository.

| In the app | API result | Script status |
| --- | --- | --- |
| you can save it | `true` | `free` |
| username is already taken | `USERNAME_OCCUPIED` | `taken` |
| listed for sale | `USERNAME_PURCHASE_AVAILABLE` | `sale` |
| invalid username | `USERNAME_INVALID` | `reserved` |

`USERNAME_INVALID` also comes back for a well-formed name. `fsb420` and `fsb555` had empty pages, and the client still refused them. `fsb999` had an empty `t.me` page and was already for sale on Fragment.

## Run

```text
python check.py --expand zovXX
python check.py --http zovXX zovXXX
python check.py --mt zovXX zovXXX
```

`zovXX` is `zov00`…`zov99`. `zovXXX` is `zov000`…`zov999`.

API keys and `.env` are described in the [guide](docs/api-credentials.md). From a Russian network, [my.telegram.org](https://my.telegram.org) often answers `Too many attempts`, and a VPN gets the same line. Login for this repository was never finished: Telegram delivered the code only inside the app, with no SMS and no email.

`--mt` waits `--delay` seconds between calls (0.4 by default). On `FLOOD_WAIT` it waits as long as the server says.

Statuses in the tsv:

- `free` — `checkUsername` allowed the name
- `taken` — already taken
- `sale` — buyable on Fragment only
- `reserved` — `USERNAME_INVALID` on a well-formed name
- `unknown` — `--http` only: no profile card and no listing. The page does not show whether the name is taken
- `invalid` — fails the character rules
- `error` — the request failed

Without `--mt` the script never calls a name free.
