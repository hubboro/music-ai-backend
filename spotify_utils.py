import os
import asyncio
import requests
import httpx
from urllib.parse import urlencode
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SCOPE = "playlist-modify-public playlist-modify-private"

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

def get_spotify_auth_url():
    query = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE
    })
    return f"{AUTH_URL}?{query}"

def get_token(code: str):
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=payload)
    return response.json()

def refresh_access_token(refresh_token: str):
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=payload)
    refreshed_token_data = response.json()

    if "error" in refreshed_token_data:
        print("❌ Failed to refresh access token:", refreshed_token_data["error"])
        raise HTTPException(
            status_code=401,
            detail=f"Spotify token refresh error: {refreshed_token_data['error']['message']}"
        )

    print("🔄 Refreshed Spotify token")
    return refreshed_token_data

async def _search_track(client: httpx.AsyncClient, headers: dict, song: dict):
    query = f"{song['title']} {song['artist']}"
    response = await client.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": 1}
    )
    data = response.json()
    items = data.get("tracks", {}).get("items")
    if items:
        return {
            "uri": items[0]["uri"],
            "title": items[0]["name"],
            "artist": items[0]["artists"][0]["name"]
        }
    return None

async def create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token=None, playlist_description=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    profile = requests.get("https://api.spotify.com/v1/me", headers=headers).json()
    print("👤 Spotify user profile response:", profile)

    if "error" in profile:
        raise HTTPException(status_code=401, detail=f"Spotify auth error: {profile['error']['message']}")

    user_id = profile["id"]

    playlist_title = playlist_name if isinstance(playlist_name, str) and playlist_name.strip() else "Butterfly Playlist"
    description_clean = playlist_description or "Butterfly generated: a musical vibe"

    playlist_response = requests.post(
        f"https://api.spotify.com/v1/users/{user_id}/playlists",
        headers=headers,
        json={"name": playlist_title, "description": description_clean, "public": True}
    ).json()

    if "error" in playlist_response:
        raise Exception(f"Spotify error: {playlist_response['error']['message']}")

    playlist_id = playlist_response["id"]

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_search_track(client, headers, song) for song in song_list])

    uris = []
    added_songs = []
    for result in results:
        if result:
            uris.append(result["uri"])
            added_songs.append({"title": result["title"], "artist": result["artist"]})

    if uris:
        requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": uris}
        )

    return playlist_response["external_urls"]["spotify"], added_songs
