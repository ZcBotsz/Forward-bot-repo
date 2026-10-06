FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Kept for the optional future FFmpeg media-watermark phase. Normal forwarding stays cloud-to-cloud.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the full Railway/GitHub build context. The packaging step below accepts all three layouts:
# 1. zcbot/ at repository root (recommended),
# 2. zc-forward-bot/zcbot/ inside a wrapper folder, or
# 3. a phone-uploaded flattened layout where Python files were accidentally put at repository root.
COPY . /app

RUN set -eux; \
    project_root=''; requirements_file=''; \
    if [ -f /app/requirements.txt ] && [ -d /app/zcbot ]; then \
        project_root='/app'; requirements_file='/app/requirements.txt'; \
    elif [ -f /app/zc-forward-bot/requirements.txt ] && [ -d /app/zc-forward-bot/zcbot ]; then \
        project_root='/app/zc-forward-bot'; requirements_file='/app/zc-forward-bot/requirements.txt'; \
    elif [ -f /app/requirements.txt ] && [ -f /app/__main__.py ] && [ -f /app/engine.py ] && [ -f /app/config.py ]; then \
        project_root='/app/.assembled'; requirements_file='/app/requirements.txt'; \
        mkdir -p "${project_root}/zcbot/handlers"; \
        for file in __init__.py __main__.py config.py db.py engine.py modes.py plans.py services.py ui.py; do \
            test -f "/app/${file}"; cp "/app/${file}" "${project_root}/zcbot/${file}"; \
        done; \
        for file in common.py start.py settings.py manager.py forward.py admin.py input.py; do \
            test -f "/app/${file}"; cp "/app/${file}" "${project_root}/zcbot/handlers/${file}"; \
        done; \
        : > "${project_root}/zcbot/handlers/__init__.py"; \
        echo 'Assembled flattened phone upload into a zcbot package.'; \
    else \
        echo >&2 'ERROR: ZC Python source is incomplete.'; \
        echo >&2 'Expected zcbot/, zc-forward-bot/zcbot/, or the complete flattened Python file set.'; \
        find /app -maxdepth 3 -type f -printf '%p\n' >&2; \
        exit 1; \
    fi; \
    test -d "${project_root}/zcbot"; \
    pip install --upgrade pip; \
    pip install -r "${requirements_file}"

RUN mkdir -p /app/data

# Select the matching project root at runtime. Railway does not need an HTTP port for this Telegram worker.
CMD ["sh", "-ec", "if [ -d /app/zcbot ]; then cd /app; elif [ -d /app/zc-forward-bot/zcbot ]; then cd /app/zc-forward-bot; elif [ -d /app/.assembled/zcbot ]; then cd /app/.assembled; else echo >&2 'ERROR: zcbot package not found in deployed source.'; exit 1; fi; exec python -m zcbot"]
