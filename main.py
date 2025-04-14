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
    allow_origins=["*"],
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
    return JSONResponse(token_data)

@app.post("/generate_playlist")
async def generate_playlist(request: Request):
    body = await request.json()
    prompt = body.get("prompt")
    access_token = body.get("access_token")

    if not prompt or not access_token:
        return JSONResponse({"error": "Missing prompt or access token"}, status_code=400)

    song_list = get_song_list_from_prompt(prompt)
    playlist_url = create_playlist_from_prompt(song_list, access_token, prompt)

    return {"playlist_url": playlist_url}


@app.get("/")
def root():
    return {"message": "FastAPI backend for AI + Spotify is running 🎵"}