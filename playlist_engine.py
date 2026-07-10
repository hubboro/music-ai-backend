import asyncio
import os
import re
import time
from collections import deque
from copy import deepcopy
from threading import Lock

from openai_utils import V2_CANDIDATE_COUNT, generate_playlist_data, generate_playlist_strategy_data
from spotify_utils import discover_spotify_candidates, match_spotify_tracks

DEFAULT_ENGINE_VERSION = os.getenv("PLAYLIST_ENGINE_VERSION", "v1").strip().lower()
MIN_V2_VALIDATED_TRACKS = max(6, min(int(os.getenv("PLAYLIST_V2_MIN_VALIDATED_TRACKS", "10")), 24))
SHADOW_V2_TIMEOUT_SECONDS = max(15, min(int(os.getenv("PLAYLIST_V2_SHADOW_TIMEOUT_SECONDS", "45")), 180))

BUCKET_BONUS = {
    "anchor": 8,
    "discovery": 18,
    "deep_cut": 22,
    "wildcard": 14,
    "closer": 12,
}
FAMILIARITY_BONUS = {
    "known": -4,
    "medium": 8,
    "obscure": 12,
}
TARGET_BUCKET_COUNTS = {
    "anchor": (2, 3),
    "discovery": (3, 5),
    "deep_cut": (1, 3),
    "wildcard": (1, 2),
    "closer": (1, 2),
}
RECENT_TRACKS = deque(maxlen=200)
RECENT_ARTISTS = deque(maxlen=200)
RECENT_SELECTIONS_LOCK = Lock()


def _normalize_key(value):
    value = (value or "").lower().replace("&", "and")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


OVERUSED_ARTISTS = {
    _normalize_key(artist)
    for artist in {
        "Tame Impala",
        "M83",
        "MGMT",
        "Phoebe Bridgers",
        "Clairo",
        "Lorde",
        "Glass Animals",
        "Florence + The Machine",
        "Mac DeMarco",
        "Arctic Monkeys",
        "The 1975",
        "Cigarettes After Sex",
        "Beach House",
        "Rex Orange County",
    }
}
OVERUSED_TRACKS = {
    _normalize_key(track)
    for track in {
        "Electric Feel",
        "Midnight City",
        "The Less I Know The Better",
        "Motion Sickness",
        "Dog Days Are Over",
        "Sunflower",
        "Goodie Bag",
        "Sweet Disposition",
        "505",
        "Ribs",
        "Space Song",
        "Chamber Of Reflection",
        "Everybody Wants To Rule The World",
        "Dreams",
    }
}


def _normalize_artist(value):
    return _normalize_key(value)


def _normalize_track(track):
    return _normalize_key(track.get("title") or track.get("name"))


def _bucket(track):
    return track.get("bucket") or "discovery"


def _familiarity(track):
    return track.get("familiarity") or "medium"


def _energy(track):
    try:
        return min(max(float(track.get("energy", 0.5)), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.5


def _recent_count(values, item):
    if not item:
        return 0
    return sum(1 for value in values if value == item)


def _overuse_penalty(track):
    title = _normalize_track(track)
    artist = _normalize_artist(track.get("primary_artist") or track.get("artist"))
    bucket = _bucket(track)
    penalty = 0

    if title in OVERUSED_TRACKS:
        penalty += 30
    if artist in OVERUSED_ARTISTS:
        penalty += 18

    with RECENT_SELECTIONS_LOCK:
        penalty += min(_recent_count(RECENT_TRACKS, title) * 14, 42)
        penalty += min(_recent_count(RECENT_ARTISTS, artist) * 8, 32)

    if bucket == "anchor":
        penalty *= 0.55
    return penalty


def remember_selected_tracks(tracks):
    with RECENT_SELECTIONS_LOCK:
        for track in tracks or []:
            title = _normalize_track(track)
            artist = _normalize_artist(track.get("primary_artist") or track.get("artist"))
            if title:
                RECENT_TRACKS.append(title)
            if artist:
                RECENT_ARTISTS.append(artist)


def score_candidate(track, position=None, selected=None):
    selected = selected or []
    score = float(track.get("match_score") or 0)
    score += BUCKET_BONUS.get(_bucket(track), 12)
    score += FAMILIARITY_BONUS.get(_familiarity(track), 4)
    score -= _overuse_penalty(track)

    if position == 0 and _energy(track) <= 0.35:
        score += 6
    if position is not None and position >= 8 and (_bucket(track) == "closer" or _energy(track) <= 0.45):
        score += 8

    artist = _normalize_artist(track.get("artist"))
    if artist and any(_normalize_artist(item.get("artist")) == artist for item in selected):
        score -= 160

    selected_buckets = [_bucket(item) for item in selected]
    if selected_buckets.count(_bucket(track)) >= TARGET_BUCKET_COUNTS.get(_bucket(track), (0, 10))[1]:
        score -= 14
    if _familiarity(track) == "known" and sum(1 for item in selected if _familiarity(item) == "known") >= 3:
        score -= 18

    return round(score, 2)


def _select_bucket(candidates, selected, bucket, limit=1):
    pool = [candidate for candidate in candidates if _bucket(candidate) == bucket and candidate not in selected]
    ranked = sorted(pool, key=lambda item: score_candidate(item, len(selected), selected), reverse=True)
    return ranked[:limit]


def rerank_candidates(candidates, limit=10):
    selected = []

    for bucket, (minimum, _maximum) in TARGET_BUCKET_COUNTS.items():
        for candidate in _select_bucket(candidates, selected, bucket, minimum):
            if len(selected) < limit and score_candidate(candidate, len(selected), selected) > 0:
                selected.append(candidate)

    remaining = [candidate for candidate in candidates if candidate not in selected]
    while len(selected) < limit and remaining:
        next_track = max(remaining, key=lambda item: score_candidate(item, len(selected), selected))
        remaining.remove(next_track)
        if score_candidate(next_track, len(selected), selected) <= 0:
            continue
        selected.append(next_track)

    closer_candidates = [candidate for candidate in selected if _bucket(candidate) == "closer"]
    if closer_candidates:
        closer = max(closer_candidates, key=lambda item: score_candidate(item, 9, selected))
        selected = [candidate for candidate in selected if candidate is not closer] + [closer]

    return [
        {
            "title": track.get("title", ""),
            "artist": track.get("artist", ""),
            "spotify_uri": track.get("spotify_uri"),
            "match_score": track.get("match_score"),
            "bucket": _bucket(track),
            "familiarity": _familiarity(track),
            "energy": _energy(track),
        }
        for track in selected[:limit]
    ]


def _format_shadow_tracks(tracks):
    return [
        (
            f"{index + 1}. {track.get('title', '')} — {track.get('artist', '')} "
            f"[{_bucket(track)}/{_familiarity(track)}]"
        )
        for index, track in enumerate(tracks)
    ]


def _elapsed_seconds(start):
    return round(time.monotonic() - start, 2)


async def generate_playlist_v1(prompt, search_token):
    result = await asyncio.to_thread(generate_playlist_data, prompt)
    songs = result.get("songs", [])
    matched_songs = await match_spotify_tracks(songs, search_token)
    remember_selected_tracks(matched_songs)
    return {
        "name": result.get("name", "Butterfly Playlist"),
        "songs": songs,
        "matched_songs": matched_songs,
        "engine_version": "v1",
    }


async def generate_playlist_v2(prompt, search_token):
    total_start = time.monotonic()

    openai_start = time.monotonic()
    result = await asyncio.to_thread(generate_playlist_strategy_data, prompt)
    search_count = len(result.get("search_queries", [])) + len(result.get("seed_artists", []))
    print(
        "🧪 V2 timing:",
        f"openai={_elapsed_seconds(openai_start)}s",
        f"strategy_searches={search_count}",
        f"discovery_level={result.get('discovery_level', 'balanced')}",
    )

    spotify_start = time.monotonic()
    candidates = await discover_spotify_candidates(result, search_token, target_count=V2_CANDIDATE_COUNT)
    print(
        "🧪 V2 timing:",
        f"spotify_discovery={_elapsed_seconds(spotify_start)}s",
        f"candidates={len(candidates)}",
    )

    if len(candidates) < MIN_V2_VALIDATED_TRACKS:
        reason = f"discovered only {len(candidates)} tracks"
        print(
            "🧪 V2 timing:",
            f"total={_elapsed_seconds(total_start)}s",
            "status=failed",
            f"reason={reason!r}",
        )
        raise ValueError(f"V2 {reason}")

    rerank_start = time.monotonic()
    target_count = min(10, len(candidates))
    selected = rerank_candidates(candidates, limit=target_count)
    print(
        "🧪 V2 timing:",
        f"rerank={_elapsed_seconds(rerank_start)}s",
        f"selected={len(selected)}/{target_count}",
    )
    if len(selected) < target_count:
        reason = f"selected only {len(selected)}/{target_count} tracks"
        print(
            "🧪 V2 timing:",
            f"total={_elapsed_seconds(total_start)}s",
            "status=failed",
            f"reason={reason!r}",
        )
        raise ValueError(f"V2 {reason}")
    remember_selected_tracks(selected)

    print("🧪 V2 timing:", f"total={_elapsed_seconds(total_start)}s", "status=success")

    return {
        "name": result.get("name", "Butterfly Playlist"),
        "songs": candidates,
        "matched_songs": selected,
        "engine_version": "v2",
        "candidate_count": len(candidates),
        "validated_count": len(candidates),
        "target_count": target_count,
        "strategy": result,
    }


def should_run_shadow_v2():
    return os.getenv("PLAYLIST_ENGINE_SHADOW", "false").strip().lower() in {"1", "true", "yes", "on"}


def shadow_v2_config_label():
    shadow_value = os.getenv("PLAYLIST_ENGINE_SHADOW", "false").strip()
    engine_value = os.getenv("PLAYLIST_ENGINE_VERSION", "v1").strip().lower()
    return f"enabled={should_run_shadow_v2()} engine={engine_value} raw_shadow={shadow_value!r}"


async def run_shadow_v2(prompt, search_token):
    shadow_start = time.monotonic()
    try:
        print("🧪 V2 shadow started:", f"timeout={SHADOW_V2_TIMEOUT_SECONDS}s")
        result = await asyncio.wait_for(
            generate_playlist_v2(prompt, search_token),
            timeout=SHADOW_V2_TIMEOUT_SECONDS,
        )
        print(
            "🧪 V2 shadow generated:",
            result.get("name"),
            f"{len(result.get('matched_songs', []))}/{result.get('target_count', 10)} selected",
            f"from {result.get('validated_count', 0)} validated",
        )
        print("🧪 V2 shadow selected:", _format_shadow_tracks(result.get("matched_songs", [])))
    except asyncio.TimeoutError:
        print(
            "🧪 V2 shadow failed:",
            f"timed out after {SHADOW_V2_TIMEOUT_SECONDS}s",
            f"elapsed={_elapsed_seconds(shadow_start)}s",
        )
    except Exception as e:
        print("🧪 V2 shadow failed:", str(e), f"elapsed={_elapsed_seconds(shadow_start)}s")


async def generate_playlist(prompt, search_token, engine_version=None):
    engine_version = (engine_version or DEFAULT_ENGINE_VERSION).lower()

    if engine_version == "v2":
        try:
            return await generate_playlist_v2(prompt, search_token)
        except Exception as e:
            print("⚠️ V2 playlist engine failed, falling back to v1:", str(e))
            return await generate_playlist_v1(prompt, search_token)

    result = await generate_playlist_v1(prompt, search_token)
    return deepcopy(result)
