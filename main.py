from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from spotify_utils import get_spotify_auth_url, get_token, create_playlist_from_prompt
from openai_utils import get_song_list_from_prompt

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "https://butterfly-music-app.vercel.app",
    "http://localhost:5173"
                    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/login")
def login():
    auth_url = get_spotify_auth_url()
    return RedirectResponse(auth_url)


@app.get("/callback")
def callback(code: str):
    token_data = get_token(code)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    frontend_redirect = f"https://butterfly-music-app.vercel.app?token={access_token}&refresh_token={refresh_token}"
    return RedirectResponse(frontend_redirect)


@app.post("/generate_playlist")
async def generate_playlist(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt")
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")

        print("🎯 Received prompt:", prompt)
        print("🔑 Access token present:", bool(access_token))

        if not prompt or not access_token:
            return JSONResponse({"error": "Missing prompt or access token"}, status_code=400)

        song_list = get_song_list_from_prompt(prompt)
        print("🎼 Song list generated:", song_list)

        try:
            playlist_url, added_songs = create_playlist_from_prompt(song_list, access_token, prompt, refresh_token)
        except Exception as e:
            if "access token expired" in str(e).lower() and refresh_token:
                print("🔁 Token expired. Attempting refresh...")
                from spotify_utils import refresh_access_token
                new_access_token = refresh_access_token(refresh_token)
                access_token = new_access_token
                playlist_url, added_songs = create_playlist_from_prompt(song_list, access_token, prompt, refresh_token)
            else:
                raise e

        print("✅ Playlist created:", playlist_url)

        return {
            "playlist_url": playlist_url,
            "songs_added": added_songs
        }

    except Exception as e:
        print("🔥 Exception during playlist generation:", str(e))
        return JSONResponse({"error": "Internal server error", "details": str(e)}, status_code=500)


@app.get("/")
def root():
    return {"message": "FastAPI backend for AI + Spotify is running 🎵"}