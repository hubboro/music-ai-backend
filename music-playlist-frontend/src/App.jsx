import { useState, useEffect } from 'react';
import axios from 'axios';

const BACKEND = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

function App() {
  const [mode, setMode] = useState(null); // null | 'login' | 'guest'
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
      if (
        message.toLowerCase().includes('token expired') ||
        message.toLowerCase().includes('spotify auth error')
      ) {
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
    setMode(null);
    setPlaylistUrl('');
    setSongs([]);
  };

  const placeholder = placeholders.length > 0
    ? placeholders[Math.floor(Math.random() * placeholders.length)]
    : 'e.g. a sunrise on a quiet beach, dancing in the kitchen, rain on glass';

  return (
    <div className="min-h-screen bg-[#f3f4f6] py-10 px-4 font-sans">
      <div className="max-w-xl mx-auto bg-white shadow-md rounded-2xl p-6">

        <div className="flex flex-col items-center justify-center text-center mb-6">
          <img src="/butterfly-logo.png" alt="Butterfly Logo" className="w-40 h-40 mb-2" />
          <p className="text-sm text-gray-500 italic">Butterfly will turn your thoughts into playlists.</p>
        </div>

        {/* Landing — choose a path */}
        {mode === null && (
          <div className="flex flex-col items-center gap-3">
            <a
              href={`${BACKEND}/login`}
              className="w-full text-center bg-[#a7b89c] text-white px-4 py-3 rounded-md hover:bg-[#94a788] font-medium"
            >
              Login with Spotify
            </a>
            <p className="text-xs text-gray-400 text-center max-w-xs">
              Creates the playlist directly in your Spotify library.
            </p>

            <div className="flex items-center w-full gap-2 my-1">
              <hr className="flex-1 border-gray-200" />
              <span className="text-xs text-gray-400">or</span>
              <hr className="flex-1 border-gray-200" />
            </div>

            <button
              onClick={() => setMode('guest')}
              className="w-full bg-white border border-[#a7b89c] text-[#6b8f5e] px-4 py-3 rounded-md hover:bg-[#f3f4f6] font-medium"
            >
              Continue without login
            </button>
            <p className="text-xs text-gray-400 text-center max-w-xs">
              We'll create a public playlist on Butterfly's account — open the link to listen and save it to your library.
            </p>
          </div>
        )}

        {/* Prompt form */}
        {mode !== null && !playlistUrl && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-lg font-semibold text-gray-700">
                What story should your playlist tell?
              </label>
              <textarea
                className="w-full border border-gray-300 rounded-md px-3 py-4 mt-1 resize-none align-top text-base"
                placeholder={placeholder}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onInput={(e) => {
                  e.target.style.height = 'auto';
                  e.target.style.height = `${e.target.scrollHeight}px`;
                }}
                rows={2}
                required
              />
            </div>
            <button
              type="submit"
              className="w-full bg-[#a7b89c] text-white py-2 rounded-md hover:bg-[#94a788]"
              disabled={loading}
            >
              {loading ? 'Generating...' : 'Generate Playlist'}
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="w-full text-xs text-gray-400 hover:text-gray-600 mt-1"
            >
              {mode === 'login' ? 'Log out' : 'Back'}
            </button>
          </form>
        )}

        {error && <p className="text-red-600 mt-4">{error}</p>}

        {/* Result */}
        {playlistUrl && (
          <div className="mt-6">
            <h2 className="text-2xl font-bold text-gray-800 mb-1">{playlistName || 'Your Playlist'}</h2>

            {guestMode && (
              <p className="text-xs text-gray-400 mb-4">
                This playlist lives on Butterfly's account — follow it on Spotify to save it to your library.
              </p>
            )}

            <ol className="mt-2 space-y-2 list-decimal list-inside text-left">
              {songs.map((song, idx) => (
                <li key={idx}>
                  <span className="text-lg font-semibold text-gray-900">{song.title}</span>{' '}
                  <span className="text-sm text-gray-500">{song.artist}</span>
                </li>
              ))}
            </ol>

            <div className="flex gap-3 mt-4">
              <a
                href={playlistUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 text-center bg-[#a7b89c] text-white px-4 py-2 rounded-md hover:bg-[#94a788]"
              >
                Open in Spotify
              </a>
              <button
                onClick={() => { setPlaylistUrl(''); setSongs([]); setPrompt(''); }}
                className="flex-1 bg-white border border-[#a7b89c] text-[#6b8f5e] px-4 py-2 rounded-md hover:bg-[#f3f4f6]"
              >
                Generate another
              </button>
            </div>

            <button
              onClick={handleLogout}
              className="w-full text-xs text-gray-400 hover:text-gray-600 mt-3"
            >
              {mode === 'login' ? 'Log out' : 'Back to home'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
