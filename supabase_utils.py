import os
import re
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or os.getenv("SUPABASE") or "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def is_supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:44].strip("-") or "soundtrack"


def create_soundtrack_slug(playlist_name):
    return f"{_slugify(playlist_name)}-{uuid.uuid4().hex[:8]}"


def save_soundtrack(
    prompt,
    playlist_name,
    songs,
    spotify_url=None,
    generated_songs=None,
    guest_mode=True,
):
    if not is_supabase_configured():
        print("ℹ️ Supabase not configured; skipping soundtrack save")
        return None

    slug = create_soundtrack_slug(playlist_name)
    base_payload = {
        "slug": slug,
        "prompt": prompt,
        "playlist_name": playlist_name,
        "songs": songs or [],
        "spotify_url": spotify_url,
        "song_count": len(songs or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    full_payload = {
        **base_payload,
        "generated_songs": generated_songs or [],
        "guest_mode": guest_mode,
    }

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/soundtracks",
        headers=_headers(),
        json=full_payload,
        timeout=10,
    )
    if not response.ok:
        print("⚠️ Supabase full soundtrack save failed:", response.text[:240])
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/soundtracks",
            headers=_headers(),
            json=base_payload,
            timeout=10,
        )
    response.raise_for_status()
    data = response.json()
    return data[0] if isinstance(data, list) and data else None


def get_soundtrack_by_slug(slug):
    if not is_supabase_configured():
        return None

    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/soundtracks",
        headers=_headers(),
        params={"slug": f"eq.{slug}", "select": "*", "limit": "1"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return data[0] if data else None


def get_supabase_status():
    status = {
        "configured": is_supabase_configured(),
        "url_present": bool(SUPABASE_URL),
        "key_present": bool(SUPABASE_SERVICE_ROLE_KEY),
        "url_host": SUPABASE_URL.replace("https://", "").replace("http://", "").split("/")[0] if SUPABASE_URL else None,
        "soundtracks_table_reachable": False,
    }

    if not is_supabase_configured():
        return status

    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/soundtracks",
            headers=_headers(),
            params={"select": "id", "limit": "1"},
            timeout=10,
        )
        status["status_code"] = response.status_code
        status["soundtracks_table_reachable"] = response.ok
        if not response.ok:
            status["error"] = response.text[:240]
    except Exception as e:
        status["error"] = str(e)

    return status
