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
  const [placeholder, setPlaceholder] = useState('a late summer evening, windows open, nowhere to be…');
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
      .then(res => {
        const list = res.data.placeholders || [];
        if (list.length > 0) setPlaceholder(list[0]);
      })
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
      } else if (err?.response?.data?.error === 'rate_limited') {
        setError('Butterfly is taking a breather — too many playlists at once. Try again in a moment.');
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setPlaylistUrl('');
    setSongs([]);
    setPrompt('');
  };

  const handleLogout = () => {
    localStorage.removeItem('spotify_access_token');
    localStorage.removeItem('spotify_refresh_token');
    localStorage.removeItem('spotify_token_timestamp');
    setAccessToken('');
    setRefreshToken('');
    setMode(isTestRoute ? null : 'guest');
    handleReset();
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 font-body">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src="/butterfly-logo.png" alt="Butterfly" className="w-20 h-20" />
        </div>

        {/* /test landing */}
        {mode === null && isTestRoute && (
          <div className="flex flex-col gap-3">
            <a
              href={`${BACKEND}/login`}
              className="w-full text-center bg-sage-500 text-white py-3 rounded-xl hover:bg-sage-600 font-medium text-sm transition-colors"
            >
              Login with Spotify
            </a>
            <div className="flex items-center gap-3">
              <hr className="flex-1 border-sage-100" />
              <span className="text-xs text-sage-300 font-body">or</span>
              <hr className="flex-1 border-sage-100" />
            </div>
            <button
              onClick={() => setMode('guest')}
              className="w-full border border-sage-200 text-sage-600 py-3 rounded-xl hover:bg-sage-50 font-medium text-sm transition-colors"
            >
              Continue without login
            </button>
          </div>
        )}

        {/* Prompt form */}
        {mode !== null && !playlistUrl && (
          <form onSubmit={handleSubmit}>
            <label className="block font-display italic text-sage-700 text-lg mb-3 text-center">
              What story should your playlist tell?
            </label>

            {/* Writing area */}
            <div className="border-b-2 border-sage-200 focus-within:border-sage-400 transition-colors pb-1 mb-8">
              <textarea
                className="w-full bg-transparent text-sage-900 font-display italic text-lg placeholder-sage-300 focus:outline-none resize-none leading-relaxed"
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

            <div className="flex justify-center">
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 bg-sage-500 text-white text-sm font-medium px-8 py-2.5 rounded-full hover:bg-sage-600 transition-colors disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                    </svg>
                    Generating
                  </>
                ) : (
                  <>Generate <span className="opacity-70">→</span></>
                )}
              </button>
            </div>

            {(mode === 'login' || isTestRoute) && (
              <p className="text-center mt-5">
                <button type="button" onClick={handleLogout} className="text-xs text-sage-300 hover:text-sage-500 transition-colors">
                  {mode === 'login' ? 'Log out' : 'Back'}
                </button>
              </p>
            )}
          </form>
        )}

        {error && <p className="text-red-400 text-sm text-center mt-4">{error}</p>}

        {/* Result */}
        {playlistUrl && (
          <div>
            <h2 className="font-display italic text-2xl text-sage-900 text-center mb-1">{playlistName || 'Your Playlist'}</h2>

            {guestMode && (
              <p className="text-center text-xs text-sage-300 mb-5">
                Follow on Spotify to save to your library.
              </p>
            )}

            <ol className="space-y-3 mt-5 mb-7">
              {songs.map((song, idx) => (
                <li key={idx} className="flex items-baseline gap-3">
                  <span className="font-display italic text-sage-300 text-sm w-4 text-right shrink-0">{idx + 1}</span>
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-sage-900">{song.title}</span>
                    <span className="text-xs text-sage-400 ml-1.5">{song.artist}</span>
                  </div>
                </li>
              ))}
            </ol>

            <div className="flex flex-col items-center gap-3">
              <a
                href={playlistUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 bg-sage-500 text-white text-sm font-medium px-8 py-2.5 rounded-full hover:bg-sage-600 transition-colors"
              >
                Open in Spotify →
              </a>
              <button
                onClick={handleReset}
                className="text-xs text-sage-400 hover:text-sage-600 transition-colors"
              >
                Generate another
              </button>
              {(mode === 'login' || isTestRoute) && (
                <button onClick={handleLogout} className="text-xs text-sage-300 hover:text-sage-500 transition-colors">
                  {mode === 'login' ? 'Log out' : 'Back to home'}
                </button>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;
