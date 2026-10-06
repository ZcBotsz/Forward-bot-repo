# Fixing the Railway `COPY zcbot ./zcbot` build error

## What the screenshot means

Railway found `Dockerfile` and `requirements.txt`, but **did not receive the `zcbot/` source folder** in the Docker build context. The old Dockerfile stopped at:

```text
COPY zcbot ./zcbot
"/zcbot": not found
```

This is an upload/repository layout issue, not a Telegram or MongoDB issue.

Your latest screenshot shows the exact phone-upload problem: all `zcbot` package files (`engine.py`, `config.py`, `start.py`, etc.) are present, but they were uploaded individually into `/app` instead of inside `zcbot/` and `zcbot/handlers/`.

The newest Dockerfile now supports **three** layouts: a correct flat project root, a nested `zc-forward-bot/` project, and this exact flattened phone-upload layout. In the third case it safely recreates the `zcbot/handlers/` package inside the image before the app starts.

**For the repository shown in the screenshot:** replace only `Dockerfile` with the newest version from this delivery, commit it, and redeploy. The files already visible in your screenshot are the complete flattened set required by the compatibility step.

## Recommended GitHub layout for future uploads

Your repository must contain these files **together**:

```text
repo-root/
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── .env.example
├── README.md
└── zcbot/
    ├── __main__.py
    ├── config.py
    └── handlers/
```

Do **not** put only `Dockerfile`, `requirements.txt`, or `ZC_Forward_Bot.zip` into GitHub. Railway does not run Python source hidden inside a ZIP archive.

## Easiest phone-friendly repair

1. Download **`ZC_Forward_Bot_Railway.zip`** from this delivery.
2. Extract it locally. It intentionally has **no extra outer folder**.
3. In GitHub, upload all extracted files and folders into the repository root. In particular, verify that you can open:
   - `zcbot/__main__.py`
   - `zcbot/engine.py`
   - `Dockerfile`
4. Commit the upload to the branch Railway deploys (normally `main`).
5. Railway → service → **Settings** → **Root Directory**:
   - Leave it **empty** if `Dockerfile` and `zcbot/` are at your repository root.
   - Set it to `zc-forward-bot` only if your repository deliberately contains that enclosing folder.
6. Railway → **Variables**: add every required value from `.env.example`:
   `API_ID`, `API_HASH`, `BOT_TOKEN`, `MONGO_URI`, `ENCRYPTION_KEY`, and `OWNER_IDS`.
7. Redeploy the latest GitHub commit.

## Quick verification before redeploying

Open your GitHub repository in the browser. The recommended layout visibly shows `zcbot` beside `Dockerfile`. The newest Dockerfile also accepts the flattened file list shown in your screenshot and logs:

```text
Assembled flattened phone upload into a zcbot package.
```

That line confirms the automatic compatibility repair ran.

## Expected successful build section

After a correct upload, Railway build logs will include a successful `COPY . /app` step followed by one of:

```text
pip install -r /app/requirements.txt
```

or, only for a nested repository:

```text
pip install -r /app/zc-forward-bot/requirements.txt
```
