import os
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

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

def create_playlist_from_prompt(song_list, access_token, prompt="AI Playlist"):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Get user ID
    profile = requests.get("https://api.spotify.com/v1/me", headers=headers).json()
    user_id = profile["id"]
    print("🎧 Creating playlist for user_id:", user_id)

    # Generate playlist name and description
    playlist_title = f"{prompt.title()}" if len(prompt) <= 50 else "AI-Generated Playlist"
    playlist_description = f"Created with AI based on the prompt: '{prompt}'"

    # Create a new playlist
    playlist_data = {
        "name": playlist_title,
        "description": playlist_description,
        "public": True
    }

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
        search = requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": query, "type": "track", "limit": 1}
        ).json()

        items = search.get("tracks", {}).get("items")
        if items:
            uris.append(items[0]["uri"])
            added_songs.append({
                "title": song["title"],
                "artist": song["artist"]
            })

    # Add tracks to the playlist
    if uris:
        requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": uris}
        )

    return playlist_response["external_urls"]["spotify"], added_songs