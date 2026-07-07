import asyncio
import os
from copy import deepcopy

from openai_utils import generate_candidate_playlist_data, generate_playlist_data
from spotify_utils import match_spotify_tracks

DEFAULT_ENGINE_VERSION = os.getenv("PLAYLIST_ENGINE_VERSION", "v1").strip().lower()
MIN_V2_VALIDATED_TRACKS = max(10, min(int(os.getenv("PLAYLIST_V2_MIN_VALIDATED_TRACKS", "14")), 24))
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


def _normalize_artist(value):
    return " ".join((value or "").lower().replace("&", "and").split())


def _bucket(track):
    return track.get("bucket") or "discovery"


def _familiarity(track):
    return track.get("familiarity") or "medium"


def _energy(track):
    try:
        return min(max(float(track.get("energy", 0.5)), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.5


def score_candidate(track, position=None, selected=None):
    selected = selected or []
    score = float(track.get("match_score") or 0)
    score += BUCKET_BONUS.get(_bucket(track), 12)
    score += FAMILIARITY_BONUS.get(_familiarity(track), 4)

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


async def generate_playlist_v1(prompt, search_token):
    result = await asyncio.to_thread(generate_playlist_data, prompt)
    songs = result.get("songs", [])
    matched_songs = await match_spotify_tracks(songs, search_token)
    return {
        "name": result.get("name", "Butterfly Playlist"),
        "songs": songs,
        "matched_songs": matched_songs,
        "engine_version": "v1",
    }


async def generate_playlist_v2(prompt, search_token):
    result = await asyncio.to_thread(generate_candidate_playlist_data, prompt)
    candidates = result.get("candidates", [])
    validated = await match_spotify_tracks(candidates, search_token)

    if len(validated) < MIN_V2_VALIDATED_TRACKS:
        raise ValueError(f"V2 validated only {len(validated)} tracks")

    selected = rerank_candidates(validated, limit=10)
    if len(selected) < 10:
        raise ValueError(f"V2 selected only {len(selected)} tracks")

    return {
        "name": result.get("name", "Butterfly Playlist"),
        "songs": candidates,
        "matched_songs": selected,
        "engine_version": "v2",
        "candidate_count": len(candidates),
        "validated_count": len(validated),
    }


def should_run_shadow_v2():
    return os.getenv("PLAYLIST_ENGINE_SHADOW", "false").strip().lower() in {"1", "true", "yes", "on"}


def shadow_v2_config_label():
    shadow_value = os.getenv("PLAYLIST_ENGINE_SHADOW", "false").strip()
    engine_value = os.getenv("PLAYLIST_ENGINE_VERSION", "v1").strip().lower()
    return f"enabled={should_run_shadow_v2()} engine={engine_value} raw_shadow={shadow_value!r}"


async def run_shadow_v2(prompt, search_token):
    try:
        print("🧪 V2 shadow started:", f"timeout={SHADOW_V2_TIMEOUT_SECONDS}s")
        result = await asyncio.wait_for(
            generate_playlist_v2(prompt, search_token),
            timeout=SHADOW_V2_TIMEOUT_SECONDS,
        )
        print(
            "🧪 V2 shadow generated:",
            result.get("name"),
            f"{len(result.get('matched_songs', []))}/10 selected",
            f"from {result.get('validated_count', 0)} validated",
        )
        print("🧪 V2 shadow selected:", _format_shadow_tracks(result.get("matched_songs", [])))
    except asyncio.TimeoutError:
        print("🧪 V2 shadow failed:", f"timed out after {SHADOW_V2_TIMEOUT_SECONDS}s")
    except Exception as e:
        print("🧪 V2 shadow failed:", str(e))


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
