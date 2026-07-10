import os
import random
import time
from copy import deepcopy
from threading import Lock
from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

_client = None
_client_lock = Lock()
_playlist_cache = {}
_playlist_cache_lock = Lock()
PLAYLIST_CACHE_TTL_SECONDS = int(os.getenv("PLAYLIST_CACHE_TTL_SECONDS", "86400"))
PLAYLIST_CACHE_MAX_ENTRIES = int(os.getenv("PLAYLIST_CACHE_MAX_ENTRIES", "200"))
MAX_PLAYLIST_REPAIR_ATTEMPTS = max(0, min(int(os.getenv("MAX_PLAYLIST_REPAIR_ATTEMPTS", "1")), 2))
V2_CANDIDATE_COUNT = max(12, min(int(os.getenv("PLAYLIST_V2_CANDIDATE_COUNT", "24")), 40))
V2_CANDIDATE_MODEL = os.getenv("PLAYLIST_V2_MODEL", "gpt-4.1-mini")
V2_CANDIDATE_TIMEOUT_SECONDS = max(10, min(int(os.getenv("PLAYLIST_V2_OPENAI_TIMEOUT_SECONDS", "20")), 60))


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            _client = OpenAI(api_key=api_key, timeout=30.0, max_retries=1)
    return _client


def _prompt_cache_key(prompt):
    return " ".join((prompt or "").lower().split())


def _get_cached_playlist(prompt):
    key = _prompt_cache_key(prompt)
    now = time.monotonic()
    with _playlist_cache_lock:
        cached = _playlist_cache.get(key)
        if not cached:
            return None
        created_at, data = cached
        if now - created_at > PLAYLIST_CACHE_TTL_SECONDS:
            _playlist_cache.pop(key, None)
            return None
        return deepcopy(data)


def _cache_playlist(prompt, data):
    if not data.get("songs"):
        return
    key = _prompt_cache_key(prompt)
    with _playlist_cache_lock:
        if len(_playlist_cache) >= PLAYLIST_CACHE_MAX_ENTRIES:
            oldest_key = min(_playlist_cache, key=lambda item: _playlist_cache[item][0])
            _playlist_cache.pop(oldest_key, None)
        _playlist_cache[key] = (time.monotonic(), deepcopy(data))

CURATOR_SYSTEM_PROMPT = (
    "You are Butterfly, a modern music curator for casual young listeners. "
    "Your job is to turn short, messy, everyday prompts into Spotify playlists "
    "that feel emotionally accurate, listenable, and culturally current. "
    "Prioritize emotional fit over cleverness, songs people can actually imagine "
    "listening to, a mix of recognizable tracks and tasteful discoveries, and "
    "coherent flow over forced variety. You understand casual internet language: "
    "'not cringe' means cool, tasteful, and socially safe; 'main character energy' "
    "means confident, cinematic, and self-possessed; 'in an edit' means stylish, "
    "dramatic, and visually energetic; 'glow up' means confident, fresh, recovered, "
    "and attractive; 'angry but cute' means playful bite, not heavy rage. "
    "Avoid overly obscure picks unless they are very fitting, novelty songs, "
    "karaoke, tribute, cover, remix, sped-up, slowed, live, or instrumental versions "
    "unless explicitly requested. Avoid children's movie soundtrack singles, wedding "
    "party clichés, corporate party songs, and aggressively off-mood tracks unless "
    "the prompt clearly asks for them. Avoid artist/title pairs you are not confident are "
    "real Spotify-searchable tracks. Avoid chaotic genre jumps and overly poetic "
    "playlist names that overuse words like midnight, velvet, echoes, whispers, "
    "or tides. Return structured JSON only."
)

PLAYLIST_RULES = (
    "- Interpret the prompt like a real young person typed it casually\n"
    "- Choose exactly 10 songs that genuinely capture the feeling\n"
    "- Include enough recognizable songs that the user feels understood, then add tasteful discoveries\n"
    "- Aim for roughly 4-6 recognizable songs and 4-6 tasteful discoveries\n"
    "- Keep the playlist coherent; do not force genre or era variety\n"
    "- Avoid one jarring outlier track that breaks the user's mood, even if the song is popular\n"
    "- Use modern indie, pop, alternative, R&B, electronic, hip-hop, and older classics only when they truly fit\n"
    "- Use exact artist names and song titles as they appear on Spotify\n"
    "- Avoid karaoke, tribute, cover, sped-up, slowed, live, remix, or instrumental versions unless the user asks for them\n"
    "- For prompts like 'not cringe', avoid children's movie soundtrack singles, wedding party clichés, and corporate party songs\n"
    "- Avoid repeating the same artist more than once unless the prompt strongly calls for it\n"
    "- Give the playlist a natural name, 2-5 words, that evokes the mood without sounding overly poetic\n"
)

REPAIR_SYSTEM_PROMPT = (
    "You are a strict playlist QA editor for Butterfly. Review generated playlist JSON "
    "for a casual young listener. Return corrected structured JSON only. Do not explain."
)

V2_STRATEGY_SYSTEM_PROMPT = (
    "You are Butterfly's playlist strategy planner. Do not choose songs. "
    "Turn a short user prompt into a practical Spotify discovery strategy that a backend can search. "
    "Name the emotional palette, adjacent genres, useful seed artists, and search phrases. "
    "Prefer fresh, specific taste directions over obvious prompt-word matches. "
    "Avoid defaulting to the same indie-pop canon. Return structured JSON only."
)
V2_CANDIDATE_SYSTEM_PROMPT = (
    "You are Butterfly's real-track-first music curator. Create a compact candidate pool "
    "for a playlist engine, not a final playlist. Prioritize real, Spotify-searchable artist/title "
    "pairs over cleverness. Return structured JSON only."
)

def _parse_playlist_json(content: str):
    try:
        data = json.loads(content)
        if isinstance(data, dict) and isinstance(data.get("songs"), list) and data.get("name"):
            return data
    except Exception as e:
        print("❌ Error parsing OpenAI JSON:", e)
    return {"name": "Untitled Playlist", "songs": []}

def _clean_playlist_data(data):
    name = str(data.get("name") or "Untitled Playlist").strip()
    songs = []

    for song in data.get("songs", []):
        if not isinstance(song, dict):
            continue
        title = str(song.get("title") or "").strip()
        artist = str(song.get("artist") or "").strip()
        if title and artist:
            songs.append({"title": title, "artist": artist})

    return {"name": name, "songs": songs[:10]}


def _clean_candidate_data(data):
    name = str(data.get("name") or "Untitled Playlist").strip()
    candidates = []
    valid_buckets = {"anchor", "discovery", "deep_cut", "wildcard", "closer"}
    valid_familiarity = {"known", "medium", "obscure"}

    for candidate in data.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        title = str(candidate.get("title") or "").strip()
        artist = str(candidate.get("artist") or "").strip()
        if not title or not artist:
            continue
        bucket = str(candidate.get("bucket") or "discovery").strip().lower()
        familiarity = str(candidate.get("familiarity") or "medium").strip().lower()
        try:
            energy = float(candidate.get("energy", 0.5))
        except (TypeError, ValueError):
            energy = 0.5
        candidates.append({
            "title": title,
            "artist": artist,
            "bucket": bucket if bucket in valid_buckets else "discovery",
            "familiarity": familiarity if familiarity in valid_familiarity else "medium",
            "energy": min(max(energy, 0.0), 1.0),
        })

    return {"name": name, "candidates": candidates[:V2_CANDIDATE_COUNT]}


def _clean_string_list(data, key, limit=8):
    values = data.get(key, [])
    if not isinstance(values, list):
        return []

    cleaned = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        normalized = " ".join(text.lower().split())
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(text[:80])
        if len(cleaned) >= limit:
            break
    return cleaned


def _clean_strategy_data(data):
    valid_curves = {"soft", "steady", "rising", "peak_then_land", "mixed"}
    valid_discovery = {"balanced", "deep", "familiar"}
    name = str(data.get("name") or "Butterfly Playlist").strip()
    energy_curve = str(data.get("energy_curve") or "mixed").strip().lower()
    discovery_level = str(data.get("discovery_level") or "balanced").strip().lower()

    return {
        "name": name[:80] or "Butterfly Playlist",
        "moods": _clean_string_list(data, "moods", limit=5),
        "genres": _clean_string_list(data, "genres", limit=6),
        "seed_artists": _clean_string_list(data, "seed_artists", limit=8),
        "avoid_artists": _clean_string_list(data, "avoid_artists", limit=10),
        "avoid_tracks": _clean_string_list(data, "avoid_tracks", limit=10),
        "search_queries": _clean_string_list(data, "search_queries", limit=8),
        "energy_curve": energy_curve if energy_curve in valid_curves else "mixed",
        "discovery_level": discovery_level if discovery_level in valid_discovery else "balanced",
    }

def _normalize_artist(artist: str):
    return " ".join(artist.lower().replace("&", "and").split())

def _find_duplicate_artists(songs):
    seen = set()
    duplicates = []

    for song in songs:
        artist = song.get("artist", "")
        normalized_artist = _normalize_artist(artist)
        if not normalized_artist:
            continue
        if normalized_artist in seen and artist not in duplicates:
            duplicates.append(artist)
        seen.add(normalized_artist)

    return duplicates

def _build_repair_notes(data):
    notes = []
    name = data.get("name", "")
    songs = data.get("songs", [])
    duplicate_artists = _find_duplicate_artists(songs)

    generic_name_terms = ("vibe", "vibes", "mood", "moods")
    if any(term in name.lower().split() for term in generic_name_terms):
        notes.append(
            "Playlist name sounds generic. Rename it to a natural, specific 2-5 word title without using vibe, vibes, mood, or moods."
        )
    if len(songs) != 10:
        notes.append(f"Playlist has {len(songs)} songs; return exactly 10.")
    if duplicate_artists:
        notes.append(
            "Duplicate artists found: "
            + ", ".join(duplicate_artists)
            + ". Replace all duplicate-artist entries except the first occurrence."
        )

    return notes

def _repair_playlist_data(prompt: str, data, extra_notes=None):
    cleaned = _clean_playlist_data(data)
    notes = _build_repair_notes(cleaned)
    if extra_notes:
        notes.extend(extra_notes)
    issue_text = "\n".join(f"- {note}" for note in notes) if notes else "- General title/artist accuracy and taste check."

    response = _get_client().chat.completions.create(
        model="gpt-4.1-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": REPAIR_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"Original user prompt: {prompt}\n\n"
                    f"Playlist JSON to repair:\n{json.dumps(cleaned, ensure_ascii=False)}\n\n"
                    f"Known issues to fix:\n{issue_text}\n\n"
                    "Repair rules:\n"
                    "- Make the smallest set of changes needed to fix the known issues\n"
                    "- Keep the same overall mood and intent\n"
                    "- Return exactly 10 songs\n"
                    "- Trim whitespace from all titles and artists\n"
                    "- Verify every object has title as the song title and artist as the performing artist\n"
                    "- Fix obvious title/artist swaps\n"
                    "- No artist may appear more than once in the final playlist\n"
                    "- When replacing a duplicate artist, choose a different artist that is not already in the playlist\n"
                    "- Replace suspicious karaoke, tribute, cover, sped-up, slowed, live, remix, or instrumental versions unless the prompt asks for them\n"
                    "- If you are unsure about a song being real and Spotify-searchable, replace it with a safer real track that fits\n"
                    "- Keep the playlist name natural, specific, 2-5 words, and do not use vibe, vibes, mood, or moods\n\n"
                    "Return JSON: {\"name\": \"...\", \"songs\": [{\"title\": \"...\", \"artist\": \"...\"}, ...]}"
                )
            }
        ]
    )
    return _clean_playlist_data(_parse_playlist_json(response.choices[0].message.content))

def _validate_and_repair_playlist_data(prompt: str, data):
    cleaned = _clean_playlist_data(data)
    repaired = cleaned

    for attempt in range(MAX_PLAYLIST_REPAIR_ATTEMPTS):
        remaining_notes = _build_repair_notes(repaired)
        if not remaining_notes:
            break
        repaired = _repair_playlist_data(
            prompt,
            repaired,
            extra_notes=(
                ["A previous result failed validation. Fix the listed issues without introducing new duplicate artists."]
                if attempt
                else None
            ),
        )

    return _clean_playlist_data(repaired)

def generate_playlist_data(prompt: str):
    cached = _get_cached_playlist(prompt)
    if cached:
        return cached

    response = _get_client().chat.completions.create(
        model="gpt-4.1-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": CURATOR_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"Create a Spotify playlist for this prompt: '{prompt}'\n\n"
                    "Rules:\n"
                    f"{PLAYLIST_RULES}\n"
                    "Return JSON: {\"name\": \"...\", \"songs\": [{\"title\": \"...\", \"artist\": \"...\"}, ...]}"
                )
            }
        ]
    )

    try:
        data = _parse_playlist_json(response.choices[0].message.content)
        result = _validate_and_repair_playlist_data(prompt, data)
        _cache_playlist(prompt, result)
        return result
    except Exception as e:
        print("❌ Error generating or repairing playlist:", e)
        return _clean_playlist_data(_parse_playlist_json(response.choices[0].message.content))


def generate_candidate_playlist_data(prompt: str):
    response = (
        _get_client()
        .with_options(timeout=V2_CANDIDATE_TIMEOUT_SECONDS, max_retries=0)
        .chat.completions.create(
            model=V2_CANDIDATE_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": V2_CANDIDATE_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a real-track-first Spotify candidate pool for this prompt: '{prompt}'\n\n"
                        f"Return exactly {V2_CANDIDATE_COUNT} candidates if possible.\n"
                        "Candidate mix:\n"
                        "- 3-5 anchor tracks: emotionally fitting and somewhat recognizable\n"
                        "- 6-9 discovery tracks: fresh, saveable, and very likely to exist on Spotify\n"
                        "- 2-4 deep cuts: underplayed but still searchable\n"
                        "- 1-2 wildcard tracks: surprising but emotionally defensible\n"
                        "- 1-2 closer/opener candidates with strong sequencing potential\n\n"
                        "Rules:\n"
                        "- Playlist name must be natural, elegant, 2-5 words, and easy to show in the app\n"
                        "- Playlist name must not use jokes, commas, slang filler, apostrophe decades like 90's, or phrases like 'but not only'\n"
                        "- Prefer real Spotify-searchable tracks over obscure or poetic guesses\n"
                        "- Do not choose songs just because their titles contain words from the user prompt\n"
                        "- Mood match matters more than title-word match\n"
                        "- Avoid repeating artists\n"
                        "- Avoid tracks that feel overused for generic prompt playlists unless they are perfect\n"
                        "- Use exact artist names and song titles as they appear on Spotify\n"
                        "- Avoid fake, uncertain, karaoke, tribute, cover, sped-up, slowed, live, remix, or instrumental versions\n"
                        "- Each candidate needs bucket, familiarity, and energy from 0 to 1\n\n"
                        "Return JSON: {\"name\": \"...\", \"candidates\": "
                        "[{\"title\": \"...\", \"artist\": \"...\", \"bucket\": \"anchor|discovery|deep_cut|wildcard|closer\", "
                        "\"familiarity\": \"known|medium|obscure\", \"energy\": 0.5}, ...]}"
                    )
                }
            ],
        )
    )

    try:
        data = json.loads(response.choices[0].message.content)
        return _clean_candidate_data(data)
    except Exception as e:
        print("❌ Error generating candidate playlist:", e)
        return {"name": "Untitled Playlist", "candidates": []}


def generate_playlist_strategy_data(prompt: str):
    response = (
        _get_client()
        .with_options(timeout=V2_CANDIDATE_TIMEOUT_SECONDS, max_retries=0)
        .chat.completions.create(
            model=V2_CANDIDATE_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": V2_STRATEGY_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a Spotify discovery strategy for this prompt: '{prompt}'\n\n"
                        "Rules:\n"
                        "- Do not return song titles\n"
                        "- Use seed artists as search starting points, not mandatory playlist inclusions\n"
                        "- Choose seed artists from adjacent scenes, eras, and subgenres, not only the most obvious names\n"
                        "- Include search_queries that Spotify search can use directly, such as genre, scene, mood, era, or artist-adjacent phrases\n"
                        "- Include avoid_artists and avoid_tracks only when they are overused, obvious, or likely to make the playlist boring\n"
                        "- Keep the playlist name natural, elegant, 2-5 words, and easy to show in the app\n"
                        "- Playlist name must not use jokes, commas, slang filler, apostrophe decades like 90's, or phrases like 'but not only'\n"
                        "- discovery_level should be balanced unless the prompt clearly asks for very familiar or very obscure music\n\n"
                        "Return JSON: {"
                        "\"name\": \"...\", "
                        "\"moods\": [\"...\"], "
                        "\"genres\": [\"...\"], "
                        "\"seed_artists\": [\"...\"], "
                        "\"avoid_artists\": [\"...\"], "
                        "\"avoid_tracks\": [\"...\"], "
                        "\"search_queries\": [\"...\"], "
                        "\"energy_curve\": \"soft|steady|rising|peak_then_land|mixed\", "
                        "\"discovery_level\": \"balanced|deep|familiar\""
                        "}"
                    )
                }
            ],
        )
    )

    try:
        data = json.loads(response.choices[0].message.content)
        return _clean_strategy_data(data)
    except Exception as e:
        print("❌ Error generating playlist strategy:", e)
        return _clean_strategy_data({"name": "Butterfly Playlist"})

def generate_prompt_placeholders():
    try:
        path = os.path.join(os.path.dirname(__file__), "placeholders.json")
        with open(path) as f:
            examples = json.load(f)
        return [random.choice(examples)]  # nosec B311
    except Exception as e:
        print("🔥 Error loading placeholders:", str(e))
        return ["a late summer evening, windows open, nowhere to be"]
