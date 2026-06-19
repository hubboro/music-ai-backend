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

def generate_prompt_placeholders():
    try:
        path = os.path.join(os.path.dirname(__file__), "placeholders.json")
        with open(path) as f:
            examples = json.load(f)
        return [random.choice(examples)]  # nosec B311
    except Exception as e:
        print("🔥 Error loading placeholders:", str(e))
        return ["a late summer evening, windows open, nowhere to be"]
