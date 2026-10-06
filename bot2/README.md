# ZC Forward Bot

A copy-based Telegram channel forwarding bot with a button UI, encrypted managed bot/userbot credentials, manually granted plans, duplicate protection, filters and ZC Manager caption modes.

> **Use only with content and channels you are entitled to access and redistribute.** This project deliberately does **not** bypass Telegram's protected-content / `noforwards` controls. A userbot login can carry an account-limitation or ban risk; users are shown a warning before phone/session login.

## What is included

- Main Telegram bot UI: `/start`, Help, About, live status, plans, subscription details and settings.
- Managed bot tokens and userbot session strings encrypted using a Fernet key before they enter MongoDB.
- Phone and string-session userbot login. Setup messages containing secrets are deleted after reading. OTPs must be sent with the `ZC` prefix, for example `ZC12345`.
- Paid-plan feature gates and an owner-only admin panel for grants, revoke, broadcast, ban and unban.
- Range forwarding in ascending order, live channel forwarding, checkpoints, restart recovery, one active job per user, job progress and FloodWait sleeps.
- Content filters, duplicate protection, per-user optional MongoDB duplicate store, caption templates, inline buttons and the ZC modes described in the specification.
- `copy_message` is used for media, so the VPS does not download media merely to forward it.

## Before you start

You need:

1. A Telegram account to create the **main manager bot** in [@BotFather](https://t.me/BotFather).
2. Telegram `API_ID` and `API_HASH` from [my.telegram.org/apps](https://my.telegram.org/apps). These are needed for the managed bots/userbots.
3. A MongoDB database. The free MongoDB Atlas M0 tier is enough to begin.
4. An always-on Linux VPS or Docker host.
5. Python **3.11+** if not using Docker.

## Create MongoDB Atlas (free)

1. Sign in at [MongoDB Atlas](https://www.mongodb.com/atlas/database).
2. Create a free shared cluster.
3. Create a database user with a long password.
4. Under **Network Access**, allow the public IP address of the server running this bot. For a quick test you can allow `0.0.0.0/0`, but a single VPS IP is safer.
5. Press **Connect → Drivers → Python**, copy the `mongodb+srv://...` URI, and replace its username/password.
6. Put that URI in `MONGO_URI` in `.env`.

## Setup with Docker (recommended)

1. Upload or unzip this project on the VPS.
2. Create the main manager bot in **@BotFather** and copy its token.
3. Create `.env` from the example:

   ```bash
   cp .env.example .env
   ```

4. Open `.env` and set `API_ID`, `API_HASH`, `BOT_TOKEN`, `MONGO_URI`, and your numeric `OWNER_IDS`.
5. Generate a Fernet key and paste it into `ENCRYPTION_KEY`:

   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

6. Start the service:

   ```bash
   docker compose up -d --build
   ```

7. View logs:

   ```bash
   docker compose logs -f
   ```

8. Open the main bot in Telegram and send `/start`.

To update after changing source code:

```bash
docker compose up -d --build
```

## Railway deployment

Use the flat `ZC_Forward_Bot_Railway.zip` delivery when uploading from a phone. The `zcbot/` folder must be present beside `Dockerfile` in the GitHub repository Railway deploys; do **not** upload only a ZIP archive. See [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) for the exact repair steps and Railway Root Directory setting.

## Setup without Docker

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env as described above
python -m zcbot
```

For a production non-Docker service, run it with a `systemd` unit configured with `Restart=always` and the project directory as `WorkingDirectory`.

## First use in Telegram

1. Send `/start` to the main bot.
2. Open **Settings → Bots**.
3. Add a bot token, or add a userbot. A managed bot/userbot must be an administrator in every **target** channel where it posts.
4. For a private source, the userbot must be a legitimate member of that source. Do not use this bot to evade protected content settings.
5. The owner uses `/admin → Grant Plan` after an offline purchase. Plans are manual; no payment gateway is included.
6. A Plus or higher user can run `/forward`, select an identity, source, target, skip count and final message ID/link, then confirm.
7. Use **Settings → ZC Manager** before beginning a job to configure applicable modes. The mode settings are snapshotted for that job.

## Owner / admin notes

- `OWNER_IDS` contains **numeric Telegram IDs**, not usernames. You can get your ID from a trusted ID bot or from your own bot's logs during development.
- Plan prices are display-only. The admin panel grants plans for a selected number of days.
- Never commit `.env`, logs, MongoDB URI, bot tokens or exported sessions to Git.
- Stored bot tokens, exported session strings and per-user duplicate MongoDB URIs are encrypted at rest with `ENCRYPTION_KEY`. **Back up this key securely**: changing it makes existing encrypted credentials unreadable.
- The bot does not log secret values. Do not manually enable verbose HTTP/MTProto logging on a shared server.

## Server needs

A forwarding-only deployment is network-bound:

- **Start:** 1 vCPU, 1 GB RAM, 5–10 GB disk is sufficient for a modest deployment.
- **Comfortable:** 1–2 vCPU and 2 GB RAM.
- **MongoDB:** Atlas M0 works for an initial small deployment.
- **Network:** stable, always-on connection; use Ubuntu 22.04/24.04 or equivalent.
- **Video/image watermarking later:** actual FFmpeg processing should use 2 vCPU, 2–4 GB RAM and additional disk. The current watermark mode edits captions; it does not alter media bytes.

## Important implementation limits

- Telegram controls access. A bot needs appropriate source access and target post permission. Some public/private and protected-content configurations will be refused by Telegram and are reported cleanly.
- Live forwarding requires the selected managed identity to receive channel updates. Keep the service running; jobs are stored and reattached on restart.
- Per-user personal MongoDB URIs are used for duplicate records only. The main bot database remains the source of truth for users/jobs/settings.
- Formatting is carried as Telegram HTML where possible. Complex malformed source markup may be normalized by Telegram.
- Telegram may rate-limit large ranges or userbot logins. Flood waits are slept exactly; do not run multiple instances against the same MongoDB/job set.

## Assumptions made for unfinished visual details

The supplied specification marked these as open. Sensible defaults are implemented:

1. Settings has nine entries: Bots, Caption, Database, Filters, Button, ZC Manager, Skip Rules, My Jobs and Reset.
2. Button colours use emoji (green add/confirm, red delete/cancel, blue navigation), because standard Telegram inline buttons do not provide portable colours.
3. Default filters are Text, Photo, Video, Document, Audio, Voice, Animation/GIF, Sticker, Poll and Video Note.
4. Numbering and Bullets are gated at Infinity+.
5. Theta appends a linked `Source post` line at the end of the generated caption.
6. Course Seller appends `Extracted by: {seller}` and supports before/after placement.
7. The assumed small-caps Unicode UI converter is used; no external font file is needed.
8. The price currency symbol is omitted until the owner confirms it.

## Tests

Run the test and quality suite after installing the development tools:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q zcbot tests
ruff check .
ruff format --check .
mypy zcbot tests
bandit -q -r zcbot
```

The included 13 tests cover plan gates, pure caption/filter/mode transformations, source-link parsing, protected small-caps UI tokens, fresh per-user settings, and Telegram `send_message`/`copy_message` argument contracts. Real Telegram login, permissions, forwarding, FloodWait and admin broadcast must be smoke-tested with your own test channels and test accounts before production use.
