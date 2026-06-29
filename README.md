# Butterfly 🦋

**Turn your thoughts into Spotify playlists using AI.**

Butterfly is a full-stack web app where users describe a mood, feeling, or theme and instantly get a curated 10-song Spotify playlist — no account required.

**Live demo:** [butterfly-music-app.vercel.app](https://butterfly-music-app.vercel.app)

---

## How it works

1. User enters a prompt — *"a late summer evening, windows open, nowhere to be"*
2. GPT-4.1 mini acts as a music curator and generates a playlist name + 10 songs
3. The backend searches Spotify for each track (in parallel) and creates a public playlist
4. User gets a link to open and follow on Spotify — no login needed

Optionally, users can log in with their own Spotify account to have playlists created directly in their library.

---

## Tech stack

**Backend**
- Python / FastAPI
- OpenAI API (GPT-4.1 mini for playlist generation and quality checks)
- Spotify Web API (OAuth 2.0, playlist creation, track search)
- Supabase (persistent, shareable soundtrack pages)
- Async parallel track search via `httpx` + `asyncio`
- Deployed on [Render](https://render.com)

**Frontend**
- React 19 + Vite
- Tailwind CSS
- Cormorant Garamond + Plus Jakarta Sans (Google Fonts)
- Deployed on [Vercel](https://vercel.com)

---

## Project structure

```
music-ai-backend/
├── main.py              # FastAPI app, routes
├── openai_utils.py      # Playlist generation and cached placeholder selection
├── spotify_utils.py     # Spotify OAuth, playlist creation, track search
├── supabase_utils.py    # Persistent soundtrack storage and retrieval
├── supabase_schema.sql  # Soundtrack table schema
├── scripts/             # Maintenance scripts, including Supabase heartbeat
├── placeholders.json    # Cached prompt examples (no API call on page load)
├── requirements.txt
├── render.yaml          # Render deployment config
└── music-playlist-frontend/
    └── src/
        └── App.jsx      # Single-page React app
```

---

## Running locally

**Backend**

```bash
git clone https://github.com/hubboro/music-ai-backend
cd music-ai-backend
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
uvicorn main:app --reload
```

**Frontend**

```bash
cd music-playlist-frontend
npm install
cp .env.example .env  # set VITE_BACKEND_URL=http://127.0.0.1:8000
npm run dev
```

**Environment variables** — see [`.env.example`](.env.example) and [`music-playlist-frontend/.env.example`](music-playlist-frontend/.env.example).

You'll need:
- An [OpenAI API key](https://platform.openai.com)
- A [Spotify app](https://developer.spotify.com/dashboard) (Client ID + Secret)
- A Spotify refresh token for the guest playlist account (obtained via the Spotify OAuth flow with your own account)
- Optional: a Supabase project for persistent, shareable soundtrack pages

---

## Privacy and license

Butterfly stores prompts and generated soundtrack data when shareable soundtrack pages are created. See [PRIVACY.md](PRIVACY.md) for details.

The source code is released under the [MIT License](LICENSE). Security reporting guidance is in [SECURITY.md](SECURITY.md).

---

## Key design decisions

- **No login required by default** — the app uses a stored Spotify account token to create public playlists, removing all friction for new users
- **Parallel Spotify search** — all 10 track searches run concurrently, cutting response time significantly
- **OpenAI JSON mode** — guarantees structured output without fragile string parsing
- **Guest vs. logged-in flow** — users can optionally log in to get playlists in their own Spotify library; the login flow is available at `/test`
- **Cost protection** — per-IP limits, global daily caps, bounded request schemas, and a repeated-prompt cache protect OpenAI and Spotify usage

The default limits allow 5 generations per IP per hour and 50 generations globally per day. They can be changed with the environment variables documented in [`.env.example`](.env.example). The in-memory limiter is designed for the current single-process Render deployment; use a shared Redis-backed limiter before scaling to multiple instances.

---

## Supabase heartbeat

The app includes a small Render Cron Job that writes one daily operational heartbeat to Supabase. It does not call OpenAI or Spotify. The row stores lightweight health metrics such as total saved soundtracks, soundtracks created in the last 24 hours, and Spotify playlists linked in the last 24 hours.

Before enabling the cron job, run the schema in [`supabase_schema.sql`](supabase_schema.sql) so the `app_heartbeat` table exists. Then configure the cron service with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in Render.

Manual test:

```bash
python scripts/supabase_heartbeat.py --no-delay
```

---

## Development notes

The initial version was prototyped with the help of [ChatGPT](https://chatgpt.com). It was then significantly extended using [Claude Code](https://claude.ai/code), before development moved to [Codex](https://openai.com/codex/) for continued implementation, debugging, and code review. Architecture decisions and product direction were my own, with AI coding tools used as development collaborators.
