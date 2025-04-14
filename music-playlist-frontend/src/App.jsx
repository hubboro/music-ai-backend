// App.jsx
import { useState, useEffect } from 'react';
import axios from 'axios';

function App() {
  const [prompt, setPrompt] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const token = queryParams.get('token');

    if (token) {
      setAccessToken(token);
      localStorage.setItem('spotify_access_token', token);
      window.history.replaceState({}, document.title, '/');
    } else {
      const savedToken = localStorage.getItem('spotify_access_token');
      if (savedToken) setAccessToken(savedToken);
    }
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
    } catch (err) {
      console.error(err);
      setError('Something went wrong. Check the console and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f3f4f6] p-4 font-sans">
      <div className="max-w-xl mx-auto bg-white shadow-md rounded-2xl p-6">
        <div className="flex flex-col items-center justify-center text-center mb-6">
          <span className="text-5xl mb-2">🦋</span>
          <h1 className="text-4xl font-extrabold text-[#a7b89c]">Butterfly</h1>
          <p className="text-sm text-gray-500 italic">Butterfly will turn your thoughts into playlists.</p>
        </div>

        {!accessToken && (
          <a
          href={`${import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'}/login`}
            className="inline-block bg-[#a7b89c] text-white px-4 py-2 rounded-md hover:bg-[#94a788] mb-4"
          >
            Login with Spotify
          </a>
        )}

        {accessToken && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block font-medium">What story should your playlist tell?</label>
              <input
                className="w-full border border-gray-300 rounded-md px-3 py-2 mt-1"
                type="text"
                placeholder="e.g. a sunrise on a quiet beach, dancing in the kitchen, rain on glass"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
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
            <h2 className="text-xl font-semibold">Your Playlist</h2>
            <a href={playlistUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
              Open in Spotify
            </a>
            <ul className="mt-2 list-disc list-inside">
              {songs.map((song, idx) => (
                <li key={idx}>{song.title} – {song.artist}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
