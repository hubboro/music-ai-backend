import os
import asyncio
import requests
import httpx
import re
from base64 import b64encode
from difflib import SequenceMatcher
from urllib.parse import urlencode
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SCOPE = "playlist-modify-public playlist-modify-private"

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"  # nosec B105
BAD_VERSION_TERMS = (
    "karaoke",
    "tribute",
    "cover",
    "remix",
    "sped up",
    "slowed",
    "reverb",
    "instrumental",
    "Originally Performed By",
)
MIN_STRICT_MATCH_SCORE = 80
MIN_RELAXED_MATCH_SCORE = 88

def get_spotify_auth_url():
    query = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE
    })
    return f"{AUTH_URL}?{query}"

def get_app_access_token():
    """Get a fresh access token using the stored app account refresh token."""
    app_refresh_token = os.getenv("APP_SPOTIFY_REFRESH_TOKEN")
    if not app_refresh_token:
        raise HTTPException(status_code=503, detail="App Spotify account not configured")
    refreshed = refresh_access_token(app_refresh_token)
    return refreshed.get("access_token")

def get_spotify_search_token():
    """Get an app-only token for Spotify search without creating user playlists."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Spotify app credentials not configured")

    credentials = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")).decode("utf-8")
    response = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {credentials}"},
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    data = response.json()
    if not response.ok or "access_token" not in data:
        raise HTTPException(status_code=503, detail="Spotify search token error")
    return data["access_token"]

def get_token(code: str):
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=10)
    if not response.ok:
        raise HTTPException(status_code=401, detail="Spotify authorization failed")
    return response.json()

def refresh_access_token(refresh_token: str):
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=10)
    refreshed_token_data = response.json()

    if "error" in refreshed_token_data:
        print("❌ Failed to refresh access token:", refreshed_token_data["error"])
        raise HTTPException(
            status_code=401,
            detail=f"Spotify token refresh error: {refreshed_token_data['error']['message']}"
        )

    print("🔄 Refreshed Spotify token")
    return refreshed_token_data

def _normalize_text(value: str):
    value = value or ""
    value = value.lower()
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())

def _similarity(left: str, right: str):
    left_normalized = _normalize_text(left)
    right_normalized = _normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0
    if left_normalized == right_normalized:
        return 100
    return round(SequenceMatcher(None, left_normalized, right_normalized).ratio() * 100)

def _has_bad_version_marker(track: dict):
    name = track.get("name", "")
    album_name = track.get("album", {}).get("name", "")
    combined = f"{name} {album_name}".lower()
    if any(term.lower() in combined for term in BAD_VERSION_TERMS):
        return True
    return bool(re.search(r"(\(|\[|-)\s*live\b|\blive at\b|\blive from\b", combined))

def _artist_names(track: dict):
    return [artist.get("name", "") for artist in track.get("artists", [])]

def _expected_artist_parts(expected_artist: str):
    normalized = re.sub(r"\b(feat|ft|featuring)\.?\b", "&", expected_artist or "", flags=re.IGNORECASE)
    parts = [part.strip() for part in normalized.split("&")]
    return [part for part in parts if part]

def _artist_match_score(expected_artist: str, track: dict):
    artist_names = _artist_names(track)
    artist_names_joined = " ".join(artist_names)
    expected_parts = _expected_artist_parts(expected_artist)
    artist_scores = [_similarity(expected_artist, artist_names_joined)]

    for expected_part in expected_parts:
        artist_scores.extend(_similarity(expected_part, artist_name) for artist_name in artist_names)

    return max(artist_scores or [0])

def _score_track_match(song: dict, track: dict):
    title_score = _similarity(song.get("title", ""), track.get("name", ""))
    artist_score = _artist_match_score(song.get("artist", ""), track)
    popularity_score = min(track.get("popularity", 0), 100)
    penalty = 35 if _has_bad_version_marker(track) else 0

    score = (title_score * 0.5) + (artist_score * 0.4) + (popularity_score * 0.1) - penalty
    return round(score)

def _format_track_result(track: dict, score: int):
    return {
        "uri": track["uri"],
        "spotify_uri": track["uri"],
        "title": track["name"],
        "artist": ", ".join(_artist_names(track)),
        "primary_artist": _artist_names(track)[0] if _artist_names(track) else "",
        "match_score": score
    }

def _best_track_match(song: dict, items: list, minimum_score: int):
    scored_items = []
    for item in items:
        if _has_bad_version_marker(item):
            continue
        score = _score_track_match(song, item)
        if score >= minimum_score:
            scored_items.append((score, item))

    if not scored_items:
        return None

    score, track = max(scored_items, key=lambda scored_item: scored_item[0])
    return _format_track_result(track, score)


def _log_search_candidates(song: dict, items: list):
    candidates = []
    seen_ids = set()
    for item in items:
        item_id = item.get("id") or item.get("uri")
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        candidates.append(
            {
                "title": item.get("name", ""),
                "artist": ", ".join(_artist_names(item)),
                "popularity": item.get("popularity", 0),
                "bad_version": _has_bad_version_marker(item),
                "score": _score_track_match(song, item),
            }
        )

    candidates = sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)[:3]
    if candidates:
        print(f"🔎 Top Spotify candidates for {song.get('title', '')} — {song.get('artist', '')}: {candidates}")

async def _spotify_search(client: httpx.AsyncClient, headers: dict, query: str, limit: int = 5):
    response = await client.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": limit}
    )
    data = response.json()
    if not response.is_success:
        error = data.get("error") if isinstance(data, dict) else {}
        message = error.get("message") if isinstance(error, dict) else response.text[:200]
        print(f"❌ Spotify search failed ({response.status_code}): {message}")
        raise HTTPException(status_code=502, detail="Spotify search failed")
    return data.get("tracks", {}).get("items") or []

async def _search_track(client: httpx.AsyncClient, headers: dict, song: dict):
    title = song.get("title", "")
    artist = song.get("artist", "")

    strict_query = f'track:"{title}" artist:"{artist}"'
    strict_items = await _spotify_search(client, headers, strict_query)
    strict_match = _best_track_match(song, strict_items, MIN_STRICT_MATCH_SCORE)
    if strict_match:
        return strict_match

    relaxed_query = f"{title} {artist}"
    relaxed_items = await _spotify_search(client, headers, relaxed_query)
    relaxed_match = _best_track_match(song, relaxed_items, MIN_RELAXED_MATCH_SCORE)
    if relaxed_match:
        return relaxed_match

    _log_search_candidates(song, strict_items + relaxed_items)
    print(f"⚠️ Skipping weak Spotify match: {title} — {artist}")
    return None

def _dedupe_matched_tracks(results):
    matched_songs = []
    added_artists = set()
    for result in results:
        if not result:
            continue
        normalized_artist = _normalize_text(result.get("primary_artist") or result.get("artist"))
        if normalized_artist in added_artists:
            print(f"⚠️ Skipping duplicate Spotify artist: {result['title']} — {result['artist']}")
            continue
        added_artists.add(normalized_artist)
        matched_songs.append({
            "title": result["title"],
            "artist": result["artist"],
            "spotify_uri": result.get("spotify_uri") or result.get("uri"),
            "match_score": result.get("match_score"),
        })
    return matched_songs

async def match_spotify_tracks(song_list, access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_search_track(client, headers, song) for song in song_list])

    matched_tracks = _dedupe_matched_tracks(results)
    print(f"🎧 Spotify matched {len(matched_tracks)}/{len(song_list or [])} tracks")
    return matched_tracks

async def create_playlist_from_tracks(
    song_list,
    access_token,
    playlist_name,
    playlist_description=None,
    public=True,
):
    matched_songs = [song for song in song_list if song.get("spotify_uri") or song.get("uri")]
    if len(matched_songs) != len(song_list):
        matched_songs = await match_spotify_tracks(song_list, access_token)

    uris = []
    added_songs = []
    seen_uris = set()
    for song in matched_songs:
        uri = song.get("spotify_uri") or song.get("uri")
        if not uri or uri in seen_uris:
            continue
        seen_uris.add(uri)
        uris.append(uri)
        added_songs.append({
            "title": song.get("title", ""),
            "artist": song.get("artist", ""),
            "spotify_uri": uri,
            "match_score": song.get("match_score"),
        })

    if not uris:
        raise HTTPException(status_code=422, detail="No Spotify tracks matched")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    profile_response = requests.get(
        "https://api.spotify.com/v1/me",
        headers=headers,
        timeout=10,
    )
    profile = profile_response.json()

    if "error" in profile:
        raise HTTPException(status_code=401, detail=f"Spotify auth error: {profile['error']['message']}")

    user_id = profile["id"]

    playlist_title = playlist_name if isinstance(playlist_name, str) and playlist_name.strip() else "Butterfly Playlist"
    description_clean = playlist_description or "Made with Butterfly from a feeling."

    playlist_create_response = requests.post(
        f"https://api.spotify.com/v1/users/{user_id}/playlists",
        headers=headers,
        json={"name": playlist_title, "description": description_clean, "public": public},
        timeout=10,
    )
    playlist_response = playlist_create_response.json()

    if "error" in playlist_response:
        raise Exception(f"Spotify error: {playlist_response['error']['message']}")

    playlist_id = playlist_response["id"]
    add_tracks_response = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers=headers,
        json={"uris": uris},
        timeout=10,
    )
    if not add_tracks_response.ok:
        raise HTTPException(status_code=502, detail="Spotify could not add tracks")

    return playlist_response["external_urls"]["spotify"], added_songs

async def create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token=None, playlist_description=None):
    return await create_playlist_from_tracks(
        song_list,
        access_token,
        playlist_name,
        playlist_description=playlist_description,
        public=True,
    )
