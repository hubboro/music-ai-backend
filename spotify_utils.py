import os
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv
from fastapi import HTTPException
import re

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

def create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token=None, playlist_description=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Get user ID
    profile = requests.get("https://api.spotify.com/v1/me", headers=headers).json()
    print("👤 Spotify user profile response:", profile)

    if "error" in profile:
        error_message = profile["error"]["message"]
        print("❌ Failed to fetch user profile:", profile["error"])
        raise HTTPException(
            status_code=401,
            detail=f"Spotify auth error: {error_message}"
        )

    user_id = profile["id"]
    print("🎧 Creating playlist for user_id:", user_id)

    # Generate playlist name and description
    playlist_title = playlist_name if isinstance(playlist_name, str) and playlist_name.strip() else "Butterfly Playlist"
    description_clean = playlist_description or "Butterfly generated: a musical vibe"
    # Create a new playlist
    playlist_data = {
        "name": playlist_title,
        "description": description_clean,
        "public": True
    }

    print("📦 Sending playlist data to Spotify:", playlist_data)

    response = requests.post(
        f"https://api.spotify.com/v1/users/{user_id}/playlists",
        headers=headers,
        json=playlist_data
    )

    playlist_response = response.json()
    print("🧪 Spotify create playlist response:", playlist_response)
    if "error" in playlist_response:
        print("❌ Spotify playlist creation failed:", playlist_response["error"])
        raise Exception(f"Spotify error: {playlist_response['error']['message']}")

    playlist_id = playlist_response["id"]

    # Prepare list of matched URIs and track names
    uris = []
    added_songs = []

    for song in song_list:
        query = f"{song['title']} {song['artist']}"
        print(f"🔍 Searching for: {query}")
        search = requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": query, "type": "track", "limit": 1}
        ).json()
        print(f"🔎 Spotify search response: {search}")

        items = search.get("tracks", {}).get("items")
        if items:
            uris.append(items[0]["uri"])
            # print(f"✅ Matched on Spotify: {items[0]['name']} – {items[0]['artists'][0]['name']}")
            added_songs.append({
                "title": items[0]["name"],
                "artist": items[0]["artists"][0]["name"]
            })

    # Add tracks to the playlist
    if uris:
        requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": uris}
        )

    return playlist_response["external_urls"]["spotify"], added_songs

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

    print("🔄 Refreshed Spotify token:", refreshed_token_data)
    return refreshed_token_data