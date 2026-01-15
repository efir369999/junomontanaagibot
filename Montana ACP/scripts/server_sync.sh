#!/bin/bash
# Montana Server Sync (для запуска на серверах)
# Синхронизация сервера с GitHub
# Cron: */5 * * * * /root/ACP_1/Montana\ ACP/scripts/server_sync.sh

REPO_DIR="/root/ACP_1"
LOCK="/tmp/montana_sync.lock"
LOG="/var/log/montana_sync.log"

[ -f "$LOCK" ] && exit 0
touch "$LOCK"
trap "rm -f $LOCK" EXIT

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $1" >> "$LOG"; }

cd "$REPO_DIR" || exit 1

# Инициализировать git если нужно
if [ ! -d ".git" ]; then
    log "Initializing git repo"
    git init
    git remote add origin git@github.com:efir369999/junomontanaagibot.git 2>/dev/null || true
fi

# Fetch
git fetch origin main 2>/dev/null || { log "WARN: fetch failed"; exit 0; }

# Pull
BEHIND=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo "0")
if [ "$BEHIND" -gt 0 ]; then
    log "Pulling $BEHIND commits"
    git pull --rebase origin main 2>/dev/null || log "WARN: pull failed"
fi

# Commit local changes
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    log "Committing local changes"
    git add -A
    git commit -m "SERVER-SYNC: $(hostname) $(date -u '+%Y-%m-%d %H:%M UTC')" 2>/dev/null || true
fi

# Push
AHEAD=$(git rev-list origin/main..HEAD --count 2>/dev/null || echo "0")
if [ "$AHEAD" -gt 0 ]; then
    log "Pushing $AHEAD commits"
    git push origin main 2>/dev/null || log "WARN: push failed"
fi

log "Sync done: behind=$BEHIND ahead=$AHEAD"
