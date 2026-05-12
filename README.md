# Wordle ELO

Discord bot that parses the daily summary message posted by the official **Wordle Activity** (embedded app, application ID `1211781489931452447`) and maintains an ELO ranking for the friend group.

- **Input**: the Wordle APP's `Yesterday's results` message — text-only, no OCR needed
- **Output**: a leaderboard embed posted as a reply, plus `/rank`, `/leaderboard`, `/history` slash commands
- **Hosting**: WSL2 + Docker on a Windows laptop, single Discord guild
- **DB**: SQLite, file mounted from the host

See `docs/plan.md` (or the original `~/.claude/plans/unified-baking-valiant.md`) for the full design.

---

## 1. Discord Developer Portal — one-time setup

1. https://discord.com/developers/applications → **New Application** (any name, e.g. "Wordle ELO")
2. Sidebar → **Bot** → **Add Bot** → **Reset Token** → save the token (you'll paste it into `.env`)
3. On the Bot page, scroll to **Privileged Gateway Intents** and enable:
   - [x] **MESSAGE CONTENT INTENT** ← critical, the bot can't see message bodies otherwise
4. Sidebar → **OAuth2 → URL Generator**:
   - **Scopes**: `bot`, `applications.commands`
   - **Bot permissions**: `View Channel`, `Read Message History`, `Send Messages`, `Embed Links`, `Read Message History`
5. Open the generated URL, pick your friend guild, **Authorize**

## 2. `.env`

```bash
cp .env.example .env
# then fill in:
#   DISCORD_BOT_TOKEN     – from step 2 above
#   DISCORD_GUILD_ID      – right-click your guild icon → Copy Server ID (Developer Mode on)
#   WORDLE_CHANNEL_ID     – right-click the #wordle channel → Copy Channel ID
#   ADMIN_USER_ID         – your own user ID, for failure DMs (optional)
#   WORDLE_APP_ID         – default is the Activity ID; verify with fetch_sample on Day 1
```

## 3. Day 1 — verify message format

Build the image, then dump 10 recent messages from the channel:

```bash
docker compose build
docker compose run --rm bot python -m wordle_elo.scripts.fetch_sample --limit 10 --raw
```

Look for:

- The `author.id` of the Wordle APP — copy it into `WORDLE_APP_ID` if it differs from `1211781489931452447`
- The exact format of result lines (is it really `N/6: <@id>`? does `X/6` appear? `*` for hard mode?)
- Where the puzzle number appears (message body? `embed.title`? `embed.description`? embed image URL?)

If the format differs from what `parser.py` expects, adjust the regex constants at the top of `src/wordle_elo/parser.py`.

## 4. Day 2-3 — backfill

Once the parser is verified, ingest all historical messages:

```bash
docker compose run --rm bot python -m wordle_elo.scripts.backfill
# or, to start from a specific puzzle:
docker compose run --rm bot python -m wordle_elo.scripts.backfill --since-puzzle 1500
```

This is **silent** (no leaderboard posts) and **idempotent** (rerun-safe). Failures are dumped to `data/logs/backfill_failures.jsonl`.

Verify:

```bash
sqlite3 data/wordle.db "SELECT puzzle_no, COUNT(*) FROM submissions GROUP BY puzzle_no ORDER BY puzzle_no LIMIT 30"
sqlite3 data/wordle.db "SELECT user_id, display_name, elo, games_played, current_streak FROM players ORDER BY elo DESC"
```

## 5. Day 4 — go live

```bash
docker compose up -d
docker compose logs -f
```

Wait for the next 12:00 AM Wordle APP message to arrive — the bot should reply with a leaderboard embed within seconds. Then test:

- `/rank`        — your stats
- `/leaderboard` — full standings
- `/history @someone 14` — recent results

## Operations

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop | `docker compose stop` |
| Tail logs | `docker compose logs -f` |
| Backup DB | `cp data/wordle.db data/wordle.db.$(date +%F).bak` |
| Restore DB | `cp data/wordle.db.YYYY-MM-DD.bak data/wordle.db && docker compose restart` |
| Recompute all ELO from submissions | `docker compose run --rm bot python -m wordle_elo.scripts.recompute_elo` |
| Reprocess a specific puzzle (e.g. parser fix) | Delete the row from `processed_puzzles`, then run backfill |

```sql
-- Inside sqlite3 data/wordle.db:
DELETE FROM processed_puzzles WHERE puzzle_no = 1783;
DELETE FROM submissions       WHERE puzzle_no = 1783;
DELETE FROM elo_history       WHERE puzzle_no = 1783;
-- Then `docker compose run --rm bot python -m wordle_elo.scripts.backfill`
-- (use --since-puzzle 1783 to skip already-processed puzzles)
```

## Tests

```bash
# Outside Docker, in a venv:
pip install -e ".[dev]"
pytest -v
```

Or inside the running container:

```bash
docker compose exec bot pytest -v
```

## Auto-start on Windows boot

Docker Desktop's *Settings → General → Start Docker Desktop when you sign in* + the `restart: unless-stopped` policy in `docker-compose.yml` means the bot comes back automatically after a reboot. WSL2 itself starts on demand when Docker Desktop launches.

If the laptop sleeps overnight and misses the 12:00 message, the **00:30 KST catch-up scheduler** (or the next bot startup) scans the channel's recent history and processes anything missing — guaranteed by the `processed_puzzles` idempotency key.
