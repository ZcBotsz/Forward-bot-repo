# ZC Forward Bot — build report

## Built

- Python 3.11+ asynchronous Telegram bot using **Kurigram** (drop-in `pyrogram` imports) and MongoDB/Motor.
- Main UI, small-caps renderer, inline navigation, configured ZC branding/links, command menu and standard `/cancel` support.
- User registration, plans, expiry worker, manual plan transfer and owner-only administration (stats, grant/revoke, broadcast, ban/unban).
- Encrypted-at-rest bot tokens, userbot session strings and optional per-user MongoDB URIs with Fernet.
- Managed BotFather token validation and userbot phone/session-string login, including ZC-prefixed OTP validation and 2FA handling.
- Forward wizard, source/target permission validation, range copy, checkpointing, live listener attachment, restart recovery, cancellation and progress display.
- Copy-based pipeline: filters, file/keyword/size skip rules, duplicate claim, caption variables, custom buttons, Gamma/Text-only gates, Watermark, Remover/Replacer/Link Remover, Numbering, Bullets, Course Seller, Theta and Pi target handling.
- Delta setup begins a message-1-through-current-history job and then leaves live forwarding on. Unequify scans/deletes repeated media only where the selected identity has normal delete permission.
- Dockerfile, Docker Compose file, `.env.example`, README and server-sizing note.
- Railway-safe Docker build layout: copies the full source context, supports flat/nested project roots, excludes secrets through `.dockerignore`, and fails clearly when `zcbot/` was not pushed.

## Verification performed

- Installed the pinned dependency ranges; Kurigram 2.2.26 was resolved and its copy/send/login method signatures were checked against the implementation.
- `python -m compileall -q zcbot tests` — passed.
- `python -m pytest -q` — passed: **13 tests**.
- `ruff check .` and `ruff format --check .` — passed with no lint or formatting findings.
- `mypy zcbot tests` — passed with no type-check findings (Telegram framework dynamic-update limitations are documented in `pyproject.toml`).
- `bandit -q -r zcbot` — passed with no security-scan findings.
- Tests cover plan ordering, filter rules, remover/replacer precedence, hidden-link handling, caption templating, numbering/bullets/watermark/theta composition, content gates, button parsing, source-link parsing, UI small-caps protection, settings isolation, and Telegram send/copy argument contracts.
- Imported the application's main modules successfully after dependency installation.

## Not run here

This environment has no Telegram credentials, real channels, MongoDB deployment or Docker daemon. The following require owner-controlled live smoke tests before production: BotFather token validation, phone OTP/2FA, session string login, source/target permissions, history/live copy, FloodWait, recovery after restart, custom Atlas URI and broadcast delivery.

## Assumptions

See the dedicated **Assumptions made for unfinished visual details** section in `README.md`. The key defaults are emoji-based button intent, the listed 10 filters, Infinity+ for Numbering/Bullets, a trailing Theta `Source post` link, and no currency symbol until confirmed.

## Compliance limit

This bot does not bypass Telegram `noforwards` / protected-content controls. Telegram may reject copying material the chosen bot/user account is not permitted to access or redistribute.
