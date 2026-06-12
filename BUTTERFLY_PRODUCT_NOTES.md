# Butterfly Product Notes

Local notes on how Butterfly creates soundtracks, what works well, and where product quality can improve. This file is for product and implementation insights and should stay local unless we intentionally decide to publish it.

## Spotify Track Matching

- The deployed generation flow works end to end: OpenAI creates a playlist concept and track list, then Spotify search finds tracks and creates a public playlist in guest mode.
- Some Spotify search results can be low-quality matches even when the backend succeeds. Example: a generated song can resolve to a karaoke, cover, tribute, remix, or unrelated version instead of the intended original recording.
- This is not a deployment problem; it is a search-quality problem in the Spotify lookup step.
- Potential improvement: search with stricter Spotify query syntax, such as `track:"Cold Air" artist:"Natalie Imbruglia"`, then reject obvious karaoke/tribute/cover results before adding tracks.
- If strict search misses too many songs, use a fallback strategy: try exact track and artist first, then relaxed query, then skip weak matches instead of adding misleading versions.

## Mobile Backlog

- Add soundtrack sharing with either the Web Share API in the PWA or the native share sheet after Capacitor is added.
