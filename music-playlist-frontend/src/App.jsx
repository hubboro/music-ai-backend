import { useState, useEffect } from 'react';
import axios from 'axios';

const BACKEND = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

function App() {
  const isTestRoute = window.location.pathname === '/test';
  const [mode, setMode] = useState(isTestRoute ? null : 'guest');
  const [prompt, setPrompt] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [refreshToken, setRefreshToken] = useState('');
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [playlistName, setPlaylistName] = useState('');
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [placeholders, setPlaceholders] = useState([]);
  const [guestMode, setGuestMode] = useState(false);

  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const token = queryParams.get('token');
    const rToken = queryParams.get('refresh_token');

    if (token) {
      setAccessToken(token);
      localStorage.setItem('spotify_access_token', token);
      localStorage.setItem('spotify_token_timestamp', Date.now().toString());
      if (rToken) {
        setRefreshToken(rToken);
        localStorage.setItem('spotify_refresh_token', rToken);
      }
      window.history.replaceState({}, document.title, '/');
      setMode('login');
    } else {
      const savedToken = localStorage.getItem('spotify_access_token');
      const savedRefreshToken = localStorage.getItem('spotify_refresh_token');
      const tokenTimestamp = parseInt(localStorage.getItem('spotify_token_timestamp') || '0', 10);
      const tokenAge = Date.now() - tokenTimestamp;

      if (tokenAge > 55 * 60 * 1000) {
        localStorage.removeItem('spotify_access_token');
        localStorage.removeItem('spotify_refresh_token');
        localStorage.removeItem('spotify_token_timestamp');
      } else if (savedToken) {
        setAccessToken(savedToken);
        if (savedRefreshToken) setRefreshToken(savedRefreshToken);
        setMode('login');
      }
    }

    axios.get(`${BACKEND}/prompt_placeholders`)
      .then(res => setPlaceholders(res.data.placeholders || []))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setPlaylistUrl('');
    setSongs([]);

    try {
      const body = { prompt };
      if (mode === 'login') {
        body.access_token = accessToken;
        body.refresh_token = refreshToken;
      }

      const res = await axios.post(`${BACKEND}/generate_playlist`, body);
      setPlaylistUrl(res.data.playlist_url);
      setSongs(res.data.songs_added);
      setPlaylistName(res.data.playlist_name);
      setGuestMode(res.data.guest_mode);
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || '';
      if (message.toLowerCase().includes('token expired') || message.toLowerCase().includes('spotify auth error')) {
        alert('Your Spotify session expired. Please log in again.');
        setMode(null);
        setAccessToken('');
        setRefreshToken('');
        localStorage.clear();
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('spotify_access_token');
    localStorage.removeItem('spotify_refresh_token');
    localStorage.removeItem('spotify_token_timestamp');
    setAccessToken('');
    setRefreshToken('');
    setMode(isTestRoute ? null : 'guest');
    setPlaylistUrl('');
    setSongs([]);
    setPrompt('');
  };

  const placeholder = placeholders.length > 0
    ? placeholders[Math.floor(Math.random() * placeholders.length)]
    : 'e.g. a sunrise on a quiet beach, dancing in the kitchen, rain on glass';

  return (
    <div className="min-h-screen py-12 px-4 font-body flex items-start justify-center">
      <div className="w-full max-w-md">

        {/* Card */}
        <div className="bg-cream/80 backdrop-blur-sm border border-sage-100 shadow-lg shadow-sage-200/30 rounded-2xl px-8 py-10">

          {/* Header */}
          <div className="flex flex-col items-center text-center mb-8">
            <img src="/butterfly-logo.png" alt="Butterfly" className="w-24 h-24 mb-1" />
            <p className="font-display italic text-sage-400 text-base mt-1">Turn your thoughts into playlists.</p>
          </div>

          {/* Landing — /test only */}
          {mode === null && isTestRoute && (
            <div className="flex flex-col items-center gap-3">
              <a
                href={`${BACKEND}/login`}
                className="w-full text-center bg-sage-500 text-white px-4 py-3 rounded-xl hover:bg-sage-600 font-medium transition-colors text-sm"
              >
                Login with Spotify
              </a>
              <p className="text-xs text-sage-400 text-center max-w-xs">
                Creates the playlist directly in your Spotify library.
              </p>
              <div className="flex items-center w-full gap-3 my-1">
                <hr className="flex-1 border-sage-100" />
                <span className="text-xs text-sage-300">or</span>
                <hr className="flex-1 border-sage-100" />
              </div>
              <button
                onClick={() => setMode('guest')}
                className="w-full bg-white border border-sage-200 text-sage-600 px-4 py-3 rounded-xl hover:bg-sage-50 font-medium transition-colors text-sm"
              >
                Continue without login
              </button>
              <p className="text-xs text-sage-400 text-center max-w-xs">
                We'll create a public playlist on Butterfly's account — open the link to listen and save it.
              </p>
            </div>
          )}

          {/* Prompt form */}
          {mode !== null && !playlistUrl && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block font-display italic text-sage-800 text-xl mb-2">
                  What story should your playlist tell?
                </label>
                <textarea
                  className="w-full border border-sage-100 bg-white/60 rounded-xl px-4 py-3 text-sage-900 text-sm placeholder-sage-300 focus:outline-none focus:ring-2 focus:ring-sage-300 resize-none transition"
                  placeholder={placeholder}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onInput={(e) => {
                    e.target.style.height = 'auto';
                    e.target.style.height = `${e.target.scrollHeight}px`;
                  }}
                  rows={3}
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-sage-500 text-white py-3 rounded-xl hover:bg-sage-600 text-sm font-medium transition-colors disabled:opacity-60"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                    </svg>
                    Generating…
                  </span>
                ) : 'Generate Playlist'}
              </button>

              {(mode === 'login' || isTestRoute) && (
                <button type="button" onClick={handleLogout} className="w-full text-xs text-sage-300 hover:text-sage-500 transition-colors pt-1">
                  {mode === 'login' ? 'Log out' : 'Back'}
                </button>
              )}
            </form>
          )}

          {error && <p className="text-red-400 mt-4 text-sm">{error}</p>}

          {/* Result */}
          {playlistUrl && (
            <div>
              <h2 className="font-display text-2xl font-semibold text-sage-900 mb-1">{playlistName || 'Your Playlist'}</h2>

              {guestMode && (
                <p className="text-xs text-sage-400 mb-4">
                  Playlist is on Butterfly's account — follow it on Spotify to save to your library.
                </p>
              )}

              <ol className="space-y-2.5 mt-4">
                {songs.map((song, idx) => (
                  <li key={idx} className="flex items-baseline gap-3">
                    <span className="font-display text-sage-300 text-base w-4 text-right shrink-0">{idx + 1}</span>
                    <div>
                      <span className="text-sm font-medium text-sage-900">{song.title}</span>
                      <span className="text-xs text-sage-400 ml-1.5">{song.artist}</span>
                    </div>
                  </li>
                ))}
              </ol>

              <div className="flex gap-3 mt-6">
                <a
                  href={playlistUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 text-center bg-sage-500 text-white px-4 py-2.5 rounded-xl hover:bg-sage-600 text-sm font-medium transition-colors"
                >
                  Open in Spotify
                </a>
                <button
                  onClick={() => { setPlaylistUrl(''); setSongs([]); setPrompt(''); }}
                  className="flex-1 bg-white border border-sage-200 text-sage-600 px-4 py-2.5 rounded-xl hover:bg-sage-50 text-sm font-medium transition-colors"
                >
                  Generate another
                </button>
              </div>

              {(mode === 'login' || isTestRoute) && (
                <button onClick={handleLogout} className="w-full text-xs text-sage-300 hover:text-sage-500 mt-3 transition-colors">
                  {mode === 'login' ? 'Log out' : 'Back to home'}
                </button>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

export default App;
