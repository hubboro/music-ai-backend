import { useState, useEffect } from 'react';
import axios from 'axios';

function App() {
  const [prompt, setPrompt] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [playlistName, setPlaylistName] = useState('');
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [placeholders, setPlaceholders] = useState([]);

  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const token = queryParams.get('token');

    if (token) {
      setAccessToken(token);
      localStorage.setItem('spotify_access_token', token);
      localStorage.setItem('spotify_token_timestamp', Date.now().toString());
      window.history.replaceState({}, document.title, '/');
    } else {
      const savedToken = localStorage.getItem('spotify_access_token');
      const tokenTimestamp = parseInt(localStorage.getItem('spotify_token_timestamp') || '0', 10);
      const tokenAge = Date.now() - tokenTimestamp;

      // If token is older than 55 minutes (Spotify tokens expire in 60 minutes), clear it
      if (tokenAge > 10 * 60 * 1000) {
        localStorage.removeItem('spotify_access_token');
        localStorage.removeItem('spotify_token_timestamp');
      } else if (savedToken) {
        setAccessToken(savedToken);
      }
    }

    axios.get(`${import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'}/prompt_placeholders`)
      .then(res => {
        setPlaceholders(res.data.placeholders || []);
      })
      .catch(err => {
        console.error('Failed to fetch prompt placeholders:', err);
      });
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setPlaylistUrl('');
    setSongs([]);

    try {
      const res = await axios.post(`${import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'}/generate_playlist`, {
        prompt,
        access_token: accessToken
      });

      setPlaylistUrl(res.data.playlist_url);
      setSongs(res.data.songs_added);
      setPlaylistName(res.data.playlist_name);
    } catch (err) {
      console.error(err);
      const message = err?.response?.data?.detail || err?.message || '';
      if (
        message.toLowerCase().includes('token expired') ||
        message.toLowerCase().includes('spotify auth error')
      ) {
        alert('Your Spotify session expired. Please log in again.');
        window.location.href = `${import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'}/login`;
      } else {
        setError('Something went wrong. Check the console and try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f3f4f6] py-10 px-4 font-sans">
      <div className="max-w-xl mx-auto bg-white shadow-md rounded-2xl p-6">
        <div className="flex flex-col items-center justify-center text-center mb-6">
          <img src="/butterfly-logo.png" alt="Butterfly Logo" className="w-40 h-40 mb-2" />
          <p className="text-sm text-gray-500 italic">Butterfly will turn your thoughts into playlists.</p>
        </div>

        {!accessToken && (
          <div className="flex flex-col items-center mb-4">
            <a
              href={`${import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'}/login`}
              className="inline-block bg-[#a7b89c] text-white px-4 py-2 rounded-md hover:bg-[#94a788] mb-2"
            >
              Login with Spotify
            </a>
            <p className="text-xs text-gray-400 mt-1 text-center max-w-xs">
              be aware - we will create a public playlist on your Spotify account
            </p>
          </div>
        )}

        {accessToken && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-lg font-semibold text-gray-700">What story should your playlist tell?</label>
              <textarea
                className="w-full border border-gray-300 rounded-md px-3 py-4 mt-1 resize-none align-top text-base"
                placeholder={placeholders.length > 0 ? placeholders[Math.floor(Math.random() * placeholders.length)] : 'e.g. a sunrise on a quiet beach, dancing in the kitchen, rain on glass'}
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
          </form>
        )}

        {error && <p className="text-red-600 mt-4">{error}</p>}

        {playlistUrl && (
          <div className="mt-6">
            <h2 className="text-2xl font-bold text-gray-800 mb-4">{playlistName || "Your Playlist"}</h2>
            <ol className="mt-4 space-y-2 list-decimal list-inside text-left">
              {songs.map((song, idx) => (
                <li key={idx}>
                  <span className="text-lg font-semibold text-gray-900">{song.title}</span>{' '}
                  <span className="text-sm text-gray-500">{song.artist}</span>
                </li>
              ))}
            </ol>
            <a
              href={playlistUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block mt-4 bg-[#a7b89c] text-white px-4 py-2 rounded-md hover:bg-[#94a788]"
            >
              Open in Spotify
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
