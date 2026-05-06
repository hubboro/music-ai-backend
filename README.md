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
- OpenAI API (GPT-4.1 mini for playlist generation, GPT-4.1 nano for prompt suggestions)
- Spotify Web API (OAuth 2.0, playlist creation, track search)
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
├── openai_utils.py      # GPT prompts for playlist + placeholder generation
├── spotify_utils.py     # Spotify OAuth, playlist creation, track search
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

---

## Key design decisions

- **No login required by default** — the app uses a stored Spotify account token to create public playlists, removing all friction for new users
- **Parallel Spotify search** — all 10 track searches run concurrently, cutting response time significantly
- **OpenAI JSON mode** — guarantees structured output without fragile string parsing
- **Guest vs. logged-in flow** — users can optionally log in to get playlists in their own Spotify library; the login flow is available at `/test`

---

## Development notes

Built with the help of [Claude Code](https://claude.ai/code) (Anthropic's AI coding assistant) for pair programming, implementation, and debugging. Architecture decisions, product direction, and code review were my own.
