# Butterfly Product Notes

Local notes on how Butterfly creates soundtracks, what works well, and where product quality can improve. This file is for product and implementation insights and should stay local unless we intentionally decide to publish it.

## Spotify Track Matching

- The deployed generation flow works end to end: OpenAI creates a playlist concept and track list, then Spotify search finds tracks and creates a public playlist in guest mode.
- Some Spotify search results can be low-quality matches even when the backend succeeds. Example: a generated song can resolve to a karaoke, cover, tribute, remix, or unrelated version instead of the intended original recording.
- This is not a deployment problem; it is a search-quality problem in the Spotify lookup step.
- Potential improvement: search with stricter Spotify query syntax, such as `track:"Cold Air" artist:"Natalie Imbruglia"`, then reject obvious karaoke/tribute/cover results before adding tracks.
- If strict search misses too many songs, use a fallback strategy: try exact track and artist first, then relaxed query, then skip weak matches instead of adding misleading versions.

## Friend-Ready Beta Plan

1. Spotify track matching guardrails
   - Use stricter Spotify queries before relaxed fallback.
   - Score candidate tracks by title match, artist match, popularity, and bad-version keywords.
   - Skip weak matches instead of adding misleading tracks.
2. Sharing
   - Added a lightweight share action on the result page.
   - Uses Web Share API on mobile, with copy-link fallback.
3. Analytics
   - Track generation success, song count, skipped tracks, share taps, and simple feedback.
   - Avoid personal data; focus on product quality signals.

## Supabase Soundtrack Storage

- Backend env vars:
  - `SUPABASE`: Supabase project URL. `SUPABASE_URL` is also supported if we rename it later.
  - `SUPABASE_SERVICE_ROLE_KEY`: backend-only Supabase Secret API key.
- Table setup lives in `supabase_schema.sql`.
- The backend saves successful generations into the `soundtracks` table:
  - prompt
  - playlist name
  - final songs added to Spotify
  - generated songs before Spotify matching
  - Spotify playlist URL
  - song count
  - guest mode
  - share/open/feedback counters for later
- To view beta data: Supabase project -> Table Editor -> `soundtracks`.

## Mobile Backlog

- Add native share sheet integration after Capacitor is added.
