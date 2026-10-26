# Newsroom Chat Lab

A study app from the Public Tech Media Lab. Participants log in with a code, chat with
a few AI models through [Poe](https://poe.com), and the interaction is stored for researchers.

- **Back end:** FastAPI (`app.py`) with a SQLite database. It is the only part that knows the Poe API key.
- **Front end:** React + Vite (`frontend/`). It builds into `static/`, which FastAPI serves.

```
Browser (React)  ->  /api/*  ->  FastAPI  ->  Poe API
                                    |
                                 study.db  (SQLite)
```

## Run it locally

You need Python 3.10+ and Node 18+.

```bash
# 1. secrets
cp .env.example .env
# edit .env: paste your Poe key (poe.com/api_key), then generate the other two:
python3 -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(16))"   # ADMIN_TOKEN

# 2. back end
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8001

# 3. front end (second terminal)
cd frontend
npm install
npm run dev            # http://localhost:3000
```

Add a test participant (login only accepts codes already in the database):

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('study.db')
db.executescript(open('schema.sql').read())
db.execute(\"INSERT OR IGNORE INTO participants(id, created_at) VALUES ('test123', strftime('%s','now'))\")
db.commit()
"
```

Real participants come from a survey export:
`python import_codes.py survey_export.csv COLUMN_NAME` (safe to run repeatedly).

## Configuration

| Variable | Purpose |
|---|---|
| `POE_API_KEY` | Poe API key. Server only. |
| `SECRET_KEY` | Signs login cookies. |
| `ADMIN_TOKEN` | Password for the data exports. |
| `DAILY_LIMIT` | Max messages per participant per 24 h (default 100). |
| `HTTPS_ONLY` | Set to `1` in production. |
| `DB_PATH` | Database file location (default `study.db`). |

Models are listed in `models.json`. Use the **lowercase IDs the Poe API accepts**
(e.g. `gpt-5.4`, `claude-sonnet-5.5`). Restart the server after editing.

## Data collected

- `messages`: every user message and model reply, with model name and response time.
- `events`: `login`, `logout`, `page_view`, `new_chat`, `open_chat`, `model_change`,
  `download_chat`, `delete_chat`.
- When a participant deletes a chat it is only hidden from them; the data stays for the research team.

Export (needs the admin token):

```bash
curl -H "x-admin-token: $ADMIN_TOKEN" https://YOUR-SITE/admin/export.csv -o messages.csv
curl -H "x-admin-token: $ADMIN_TOKEN" https://YOUR-SITE/admin/events.csv   -o events.csv
```

## Deploy

See the steps in the project chat or follow these (Render):

1. Push this repo to GitHub (private recommended).
2. In Render choose **New > Blueprint**, select the repo. `render.yaml` and the `Dockerfile` do the rest.
3. When asked, paste `POE_API_KEY`. `SECRET_KEY` and `ADMIN_TOKEN` are generated for you.
4. Open the **Shell** tab and load participants:
   ```bash
   cat > codes.csv <<'EOF'
   code
   abc123
   def456
   EOF
   python import_codes.py codes.csv code
   ```
5. Visit your `.onrender.com` URL and log in with one of the codes.

## Redirect from LimeSurvey

In LimeSurvey go to **Settings > Text elements > End URL** and use:

```
https://YOUR-SITE/?pid={TOKEN}
```

- `{TOKEN}` works for closed surveys with participant tokens. For open surveys use
  `{SAVEDID}` or a hidden question with `{INSERTANS:SID_GID_QID}`.
- Add `&consent=1` only if the survey already collected consent; the participant then goes
  straight into the chat. Otherwise they tick the consent box once.
- The ID is removed from the address bar after the page loads.
- The ID must already be in the database. Export the same values from LimeSurvey
  (tokens or IDs) and load them with `python import_codes.py file.csv COLUMN`.

## Security checklist

- `.env`, `*.db` and `*.csv` are git-ignored. Never commit them.
- Secrets are set as environment variables on the host, not in files.
- Revoke and replace the Poe key if it is ever pasted somewhere public.
- Keep the database on the persistent disk and back it up.
