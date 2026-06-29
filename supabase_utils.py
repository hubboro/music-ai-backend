import os
import re
import uuid
from datetime import datetime, timedelta, timezone

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


def _postgrest_count(response):
    content_range = response.headers.get("Content-Range", "")
    if "/" not in content_range:
        return None

    total = content_range.rsplit("/", 1)[-1]
    if total == "*":
        return None

    try:
        return int(total)
    except ValueError:
        return None


def _count_soundtracks(params=None):
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/soundtracks",
        headers={**_headers(), "Prefer": "count=exact"},
        params={"select": "id", "limit": "1", **(params or {})},
        timeout=10,
    )
    response.raise_for_status()
    return _postgrest_count(response)


def build_heartbeat_payload(source="render-cron", status="ok", metrics=None, error=None, checked_at=None):
    checked_at = checked_at or datetime.now(timezone.utc)
    payload = {
        "run_date": checked_at.date().isoformat(),
        "source": source,
        "status": status,
        "metrics": metrics or {},
        "checked_at": checked_at.isoformat(),
    }
    if error:
        payload["error"] = str(error)[:500]
    return payload


def save_app_heartbeat(source="render-cron"):
    if not is_supabase_configured():
        raise RuntimeError("Supabase is not configured")

    checked_at = datetime.now(timezone.utc)
    since_24h = (checked_at - timedelta(hours=24)).isoformat()
    metrics = {}
    status = "ok"
    error = None

    try:
        metrics = {
            "soundtracks_total": _count_soundtracks(),
            "soundtracks_created_last_24h": _count_soundtracks({"created_at": f"gte.{since_24h}"}),
            "spotify_playlists_linked_last_24h": _count_soundtracks(
                {"created_at": f"gte.{since_24h}", "spotify_url": "not.is.null"}
            ),
        }
    except Exception as e:
        status = "degraded"
        error = f"Could not collect soundtrack metrics: {e}"

    payload = build_heartbeat_payload(source=source, status=status, metrics=metrics, error=error, checked_at=checked_at)
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/app_heartbeat",
        headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
        params={"on_conflict": "run_date,source"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return data[0] if isinstance(data, list) and data else payload


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


def update_soundtrack_spotify_url(slug, spotify_url, songs=None):
    if not is_supabase_configured() or not slug or not spotify_url:
        return None

    payload = {"spotify_url": spotify_url}
    if songs is not None:
        payload["songs"] = songs
        payload["song_count"] = len(songs or [])

    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/soundtracks",
        headers={**_headers(), "Prefer": "return=representation"},
        params={"slug": f"eq.{slug}"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return data[0] if isinstance(data, list) and data else None


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
