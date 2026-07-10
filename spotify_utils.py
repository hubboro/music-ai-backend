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
SPOTIFY_SEARCH_TIMEOUT_SECONDS = max(3, min(int(os.getenv("SPOTIFY_SEARCH_TIMEOUT_SECONDS", "6")), 20))

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


def _spotify_track_url(track: dict):
    external_urls = track.get("external_urls") or {}
    return external_urls.get("spotify")


def _track_popularity(track: dict):
    try:
        return min(max(int(track.get("popularity", 0)), 0), 100)
    except (TypeError, ValueError):
        return 0


def _discovery_familiarity(track: dict, discovery_level: str):
    popularity = _track_popularity(track)
    if discovery_level == "deep":
        if popularity >= 70:
            return "known"
        if popularity >= 35:
            return "medium"
        return "obscure"
    if discovery_level == "familiar":
        if popularity >= 45:
            return "known"
        if popularity >= 15:
            return "medium"
        return "obscure"
    if popularity >= 65:
        return "known"
    if popularity >= 25:
        return "medium"
    return "obscure"


def _discovery_bucket(source: str, index: int, discovery_level: str):
    if source == "seed_artist" and index <= 1:
        return "anchor"
    if source == "wildcard":
        return "wildcard"
    if discovery_level == "deep" or source in {"genre_mood", "scene"}:
        return "deep_cut"
    return "discovery"


def _discovery_energy(track: dict, energy_curve: str, index: int):
    if energy_curve == "soft":
        return 0.35
    if energy_curve == "rising":
        return min(0.35 + (index * 0.08), 0.9)
    if energy_curve == "peak_then_land":
        return 0.75 if index < 4 else 0.45
    if energy_curve == "steady":
        return 0.58
    return 0.5


def _format_discovery_candidate(track: dict, source: str, index: int, strategy: dict):
    artists = _artist_names(track)
    discovery_level = strategy.get("discovery_level") or "balanced"
    energy_curve = strategy.get("energy_curve") or "mixed"
    popularity = _track_popularity(track)

    return {
        "uri": track.get("uri"),
        "spotify_uri": track.get("uri"),
        "spotify_url": _spotify_track_url(track),
        "title": track.get("name", ""),
        "artist": ", ".join(artists),
        "primary_artist": artists[0] if artists else "",
        "match_score": 62 + min(popularity * 0.25, 20),
        "bucket": _discovery_bucket(source, index, discovery_level),
        "familiarity": _discovery_familiarity(track, discovery_level),
        "energy": _discovery_energy(track, energy_curve, index),
        "source": source,
        "popularity": popularity,
    }


def _strategy_list(strategy: dict, key: str, limit: int):
    values = strategy.get(key, [])
    if not isinstance(values, list):
        return []
    cleaned = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        normalized = _normalize_text(text)
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _strategy_search_specs(strategy: dict):
    specs = []
    seed_artists = _strategy_list(strategy, "seed_artists", 6)
    search_queries = _strategy_list(strategy, "search_queries", 8)
    genres = _strategy_list(strategy, "genres", 4)
    moods = _strategy_list(strategy, "moods", 4)

    for artist in seed_artists:
        specs.append((artist, "seed_artist"))
    for query in search_queries:
        specs.append((query, "scene"))
    for genre in genres:
        if moods:
            for mood in moods[:2]:
                specs.append((f"{genre} {mood}", "genre_mood"))
        else:
            specs.append((genre, "genre_mood"))

    seen = set()
    deduped = []
    for query, source in specs:
        normalized = _normalize_text(query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((query, source))
    return deduped[:18]


def _is_avoided_track(candidate: dict, strategy: dict):
    title = _normalize_text(candidate.get("title"))
    artist = _normalize_text(candidate.get("primary_artist") or candidate.get("artist"))
    avoid_artists = {_normalize_text(value) for value in _strategy_list(strategy, "avoid_artists", 20)}
    avoid_tracks = {_normalize_text(value) for value in _strategy_list(strategy, "avoid_tracks", 20)}

    if artist and artist in avoid_artists:
        return True
    return bool(title and title in avoid_tracks)


def _with_candidate_metadata(match: dict, song: dict):
    for key in ("bucket", "familiarity", "energy"):
        if song.get(key) is not None:
            match[key] = song.get(key)
    return match


def _spotify_error_message(response, fallback="Spotify request failed"):
    try:
        data = response.json()
    except ValueError:
        return response.text[:240] or fallback

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return error.get("message") or error.get("reason") or fallback
    if isinstance(error, str):
        return error
    return fallback

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
        return _with_candidate_metadata(strict_match, song)

    relaxed_query = f"{title} {artist}"
    relaxed_items = await _spotify_search(client, headers, relaxed_query)
    relaxed_match = _best_track_match(song, relaxed_items, MIN_RELAXED_MATCH_SCORE)
    if relaxed_match:
        return _with_candidate_metadata(relaxed_match, song)

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
            "bucket": result.get("bucket"),
            "familiarity": result.get("familiarity"),
            "energy": result.get("energy"),
        })
    return matched_songs

async def match_spotify_tracks(song_list, access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=SPOTIFY_SEARCH_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(*[_search_track(client, headers, song) for song in song_list])

    matched_tracks = _dedupe_matched_tracks(results)
    print(f"🎧 Spotify matched {len(matched_tracks)}/{len(song_list or [])} tracks")
    return matched_tracks


async def _discover_for_query(client: httpx.AsyncClient, headers: dict, query: str, source: str, strategy: dict):
    items = await _spotify_search(client, headers, query, limit=10)
    candidates = []
    for index, item in enumerate(items):
        if _has_bad_version_marker(item):
            continue
        candidate = _format_discovery_candidate(item, source, index, strategy)
        if not candidate.get("spotify_uri") or not candidate.get("title") or not candidate.get("artist"):
            continue
        if _is_avoided_track(candidate, strategy):
            continue
        candidates.append(candidate)
    return candidates


async def discover_spotify_candidates(strategy: dict, access_token: str, target_count: int = 24):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    search_specs = _strategy_search_specs(strategy)
    if not search_specs:
        print("🎧 Spotify discovery skipped: strategy had no search specs")
        return []

    async with httpx.AsyncClient(timeout=SPOTIFY_SEARCH_TIMEOUT_SECONDS) as client:
        groups = await asyncio.gather(
            *[
                _discover_for_query(client, headers, query, source, strategy)
                for query, source in search_specs
            ]
        )

    candidates = []
    seen_tracks = set()
    max_candidates = max(target_count, 10)
    for group in groups:
        for candidate in group:
            track_key = candidate.get("spotify_uri") or _normalize_text(
                f"{candidate.get('title')} {candidate.get('artist')}"
            )
            if not track_key or track_key in seen_tracks:
                continue
            seen_tracks.add(track_key)
            candidates.append(candidate)
            if len(candidates) >= max_candidates:
                print(
                    f"🎧 Spotify discovery found {len(candidates)} candidates "
                    f"from {len(search_specs)} strategy searches"
                )
                return candidates

    print(
        f"🎧 Spotify discovery found {len(candidates)} candidates "
        f"from {len(search_specs)} strategy searches"
    )
    return candidates

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

    playlist_title = playlist_name if isinstance(playlist_name, str) and playlist_name.strip() else "Butterfly Playlist"
    description_clean = playlist_description or "Made with Butterfly from a feeling."

    playlist_create_response = requests.post(
        "https://api.spotify.com/v1/me/playlists",
        headers=headers,
        json={"name": playlist_title, "description": description_clean, "public": public},
        timeout=10,
    )
    playlist_response = playlist_create_response.json()

    if not playlist_create_response.ok or "error" in playlist_response:
        message = _spotify_error_message(playlist_create_response, "Could not create Spotify playlist")
        print(f"❌ Spotify playlist create failed ({playlist_create_response.status_code}): {message}")
        raise HTTPException(status_code=502, detail=f"Spotify playlist create failed: {message}")

    playlist_id = playlist_response["id"]
    add_tracks_response = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/items",
        headers=headers,
        json={"uris": uris},
        timeout=10,
    )
    if not add_tracks_response.ok:
        message = _spotify_error_message(add_tracks_response, "Could not add tracks to Spotify playlist")
        print(f"❌ Spotify add tracks failed ({add_tracks_response.status_code}): {message}")
        raise HTTPException(status_code=502, detail=f"Spotify add tracks failed: {message}")

    return playlist_response["external_urls"]["spotify"], added_songs

async def create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token=None, playlist_description=None):
    return await create_playlist_from_tracks(
        song_list,
        access_token,
        playlist_name,
        playlist_description=playlist_description,
        public=True,
    )
