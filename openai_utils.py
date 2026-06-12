import os
import random
from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

    response = client.chat.completions.create(
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
    initial_notes = _build_repair_notes(cleaned)

    if not initial_notes:
        return cleaned

    repaired = _repair_playlist_data(prompt, cleaned)
    remaining_notes = _build_repair_notes(repaired)

    if remaining_notes:
        repaired = _repair_playlist_data(
            prompt,
            repaired,
            extra_notes=[
                "The previous repair still failed these checks. Fix them now without introducing new duplicate artists.",
                *remaining_notes
            ]
        )

    return _clean_playlist_data(repaired)

def generate_playlist_data(prompt: str):
    response = client.chat.completions.create(
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
        return _validate_and_repair_playlist_data(prompt, data)
    except Exception as e:
        print("❌ Error generating or repairing playlist:", e)
        return _clean_playlist_data(_parse_playlist_json(response.choices[0].message.content))

def generate_prompt_placeholders():
    try:
        path = os.path.join(os.path.dirname(__file__), "placeholders.json")
        with open(path) as f:
            examples = json.load(f)
        return [random.choice(examples)]
    except Exception as e:
        print("🔥 Error loading placeholders:", str(e))
        return ["a late summer evening, windows open, nowhere to be"]
