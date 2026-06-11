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
  const [placeholder, setPlaceholder] = useState('a late summer evening, windows open, nowhere to be...');
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

  const handlePromptInput = (e) => {
    setPrompt(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${e.target.scrollHeight}px`;
  };

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
        setError('Your Spotify session expired. Please log in again.');
        setMode(isTestRoute ? null : 'guest');
        setAccessToken('');
        setRefreshToken('');
        localStorage.clear();
      } else if (err?.response?.data?.error === 'rate_limited') {
        setError('Butterfly is taking a breather - too many playlists at once. Try again in a moment.');
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
    setError('');
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

  const hasPrompt = prompt.trim().length > 0;

  return (
    <div className="app-shell font-body text-sage-900">
      <header className="app-header">
        <button
          type="button"
          onClick={handleReset}
          className="brand-button"
          aria-label="Start a new Butterfly soundtrack"
        >
          <img src="/butterfly-logo.png" alt="" className="h-12 w-12" />
        </button>

        {(mode === 'login' || isTestRoute) && mode !== null && (
          <button
            type="button"
            onClick={handleLogout}
            className="secondary-action"
          >
            {mode === 'login' ? 'Log out' : 'Back'}
          </button>
        )}
      </header>

      <main className="app-main">
        {mode === null && isTestRoute && (
          <section className="intro-screen">
            <div>
              <p className="eyebrow">Test mode</p>
              <h1 className="screen-title">Choose how to make your soundtrack.</h1>
            </div>

            <div className="stack-actions">
              <a href={`${BACKEND}/login`} className="primary-button">
                Login with Spotify
              </a>
              <button
                type="button"
                onClick={() => setMode('guest')}
                className="quiet-button"
              >
                Continue without login
              </button>
            </div>
          </section>
        )}

        {mode !== null && !playlistUrl && (
          <form onSubmit={handleSubmit} className="composer-screen">
            <section className="composer-panel" aria-busy={loading}>
              <p className="eyebrow">Butterfly</p>
              <label htmlFor="playlist-prompt" className="composer-label">
                What should your soundtrack feel like?
              </label>

              <textarea
                id="playlist-prompt"
                className="composer-textarea"
                placeholder={placeholder}
                value={prompt}
                onChange={handlePromptInput}
                rows={6}
                required
                disabled={loading}
                autoCapitalize="sentences"
                autoComplete="off"
                autoCorrect="on"
                enterKeyHint="done"
                spellCheck="true"
              />
            </section>

            {loading && (
              <section className="creating-state" role="status" aria-live="polite">
                <div className="pulse-mark">
                  <img src="/butterfly-logo.png" alt="" className="h-8 w-8" />
                </div>
                <div>
                  <p className="creating-title">Creating your soundtrack</p>
                  <p className="creating-copy">Finding songs that fit the feeling.</p>
                </div>
              </section>
            )}

            {error && (
              <p className="toast-message" role="alert">
                {error}
              </p>
            )}

            <div className="bottom-action">
              <button
                type="submit"
                disabled={loading || !hasPrompt}
                className="primary-button"
              >
                {loading ? (
                  <span className="button-with-spinner">
                    <span className="spinner" aria-hidden="true" />
                    Creating
                  </span>
                ) : (
                  'Make my soundtrack'
                )}
              </button>
            </div>
          </form>
        )}

        {playlistUrl && (
          <section className="result-screen">
            <div className="playlist-hero">
              <p className="eyebrow">Your soundtrack</p>
              <h1 className="playlist-title">{playlistName || 'Your Soundtrack'}</h1>
              {guestMode && (
                <p className="playlist-note">
                  Follow it on Spotify to save it to your library.
                </p>
              )}
            </div>

            <ol className="track-list" aria-label="Songs in your soundtrack">
              {songs.map((song, idx) => (
                <li key={`${song.title}-${song.artist}-${idx}`} className="track-row">
                  <span className="track-number">{String(idx + 1).padStart(2, '0')}</span>
                  <div className="track-copy">
                    <span className="track-title">{song.title}</span>
                    <span className="track-artist">{song.artist}</span>
                  </div>
                </li>
              ))}
            </ol>

            <div className="bottom-action result-actions">
              <a
                href={playlistUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="primary-button"
              >
                Open in Spotify
              </a>
              <button
                type="button"
                onClick={handleReset}
                className="quiet-button"
              >
                Make another soundtrack
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
