import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import axios from 'axios';

const BACKEND = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
const HISTORY_STORAGE_KEY = 'butterfly_soundtrack_history';
const HISTORY_LIMIT = 12;

const LOADING_STORIES = [
  'Reading the mood.',
  'Finding the first song.',
  'Balancing familiar and unexpected.',
  'Looking for the hidden thread.',
  'Choosing the opening scene.',
  'Tuning the emotional weather.',
  'Skipping the obvious picks.',
  'Letting the deeper cuts in.',
  'Arranging the arc.',
  'Sending it to Spotify.'
];

const getRandomLoadingStory = (currentStory = '') => {
  const options = LOADING_STORIES.filter((story) => story !== currentStory);
  const pool = options.length > 0 ? options : LOADING_STORIES;
  return pool[Math.floor(Math.random() * pool.length)];
};

const getShareSlugFromPath = () => window.location.pathname.match(/^\/s\/([^/]+)/)?.[1] || '';

const getLocalSoundtrackUrl = (slug) => {
  if (!slug) return '';
  return `${window.location.origin}/s/${encodeURIComponent(slug)}`;
};

const normalizeSoundtrackUrl = (url) => {
  if (!url) return '';
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.pathname.startsWith('/s/')
      ? `${window.location.origin}${parsedUrl.pathname}`
      : '';
  } catch {
    return '';
  }
};

const getCurrentSoundtrackPageUrl = () => {
  const slug = getShareSlugFromPath();
  return slug ? getLocalSoundtrackUrl(decodeURIComponent(slug)) : '';
};

const showSoundtrackPageInAddressBar = (soundtrackPageUrl) => {
  if (!soundtrackPageUrl) return;

  try {
    const parsedUrl = new URL(soundtrackPageUrl);
    if (window.location.pathname !== parsedUrl.pathname) {
      window.history.replaceState({}, document.title, parsedUrl.pathname);
    }
  } catch {
    // Sharing still works from state even if the URL cannot be reflected.
  }
};

const readSoundtrackHistory = () => {
  try {
    const storedHistory = JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) || '[]');
    if (!Array.isArray(storedHistory)) return [];

    return storedHistory
      .filter((item) => (item?.playlistUrl || item?.soundtrackUrl) && item?.playlistName)
      .map((item) => ({
        id: item.id || item.soundtrackUrl || item.playlistUrl,
        playlistName: item.playlistName,
        prompt: item.prompt || 'Saved soundtrack',
        playlistUrl: item.playlistUrl,
        soundtrackUrl: normalizeSoundtrackUrl(item.soundtrackUrl),
        songs: Array.isArray(item.songs) ? item.songs : [],
        trackCount: Number.isFinite(item.trackCount) ? item.trackCount : 0,
        createdAt: item.createdAt || new Date().toISOString()
      }))
      .slice(0, HISTORY_LIMIT);
  } catch {
    return [];
  }
};

const writeSoundtrackHistory = (history) => {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
  } catch {
    // History is a convenience feature; playlist creation should still succeed.
  }
};

const copyTextToClipboard = async (text) => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to the selection-based copy path below.
  }

  const textArea = document.createElement('textarea');
  textArea.value = text;
  textArea.setAttribute('readonly', '');
  textArea.style.position = 'fixed';
  textArea.style.top = '-9999px';
  textArea.style.opacity = '0';
  document.body.appendChild(textArea);
  textArea.select();
  textArea.setSelectionRange(0, text.length);

  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  } finally {
    document.body.removeChild(textArea);
  }

  return copied;
};

const formatHistoryDate = (dateString) => {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric'
    }).format(new Date(dateString));
  } catch {
    return '';
  }
};

function App() {
  const isTestRoute = window.location.pathname === '/test';
  const shareSlug = getShareSlugFromPath();
  const textareaRef = useRef(null);
  const [mode, setMode] = useState(isTestRoute ? null : 'guest');
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [refreshToken, setRefreshToken] = useState('');
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [soundtrackUrl, setSoundtrackUrl] = useState(getLocalSoundtrackUrl(decodeURIComponent(shareSlug)));
  const [playlistName, setPlaylistName] = useState('');
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingSavedSoundtrack, setLoadingSavedSoundtrack] = useState(Boolean(shareSlug));
  const [loadingStory, setLoadingStory] = useState(() => getRandomLoadingStory());
  const [error, setError] = useState('');
  const [placeholder, setPlaceholder] = useState('a late summer evening, windows open, nowhere to be...');
  const [guestMode, setGuestMode] = useState(false);
  const [soundtrackHistory, setSoundtrackHistory] = useState([]);
  const [shareStatus, setShareStatus] = useState('');
  const [creatingShareLink, setCreatingShareLink] = useState(false);

  useEffect(() => {
    setSoundtrackHistory(readSoundtrackHistory());

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

  useEffect(() => {
    if (!shareSlug) return undefined;

    let cancelled = false;
    setLoadingSavedSoundtrack(true);
    setError('');

    axios.get(`${BACKEND}/soundtracks/${shareSlug}`)
      .then((res) => {
        if (cancelled) return;
        const data = res.data || {};
        const savedSongs = Array.isArray(data.songs) ? data.songs : [];
        const nextSoundtrackUrl = getLocalSoundtrackUrl(data.slug || decodeURIComponent(shareSlug));

        setPlaylistName(data.playlist_name || 'Your Soundtrack');
        setPlaylistUrl(data.spotify_url || '');
        setSoundtrackUrl(nextSoundtrackUrl);
        setSongs(savedSongs);
        setPrompt(data.prompt || '');
        setGuestMode(true);
        setMode('guest');
      })
      .catch(() => {
        if (!cancelled) setError('This soundtrack could not be found.');
      })
      .finally(() => {
        if (!cancelled) setLoadingSavedSoundtrack(false);
      });

    return () => {
      cancelled = true;
    };
  }, [shareSlug]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || playlistUrl || soundtrackUrl || mode === null) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const timer = window.setTimeout(() => {
      textarea.focus({ preventScroll: prefersReducedMotion });
    }, 280);

    return () => window.clearTimeout(timer);
  }, [mode, playlistUrl, soundtrackUrl]);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return undefined;

    const handleViewportChange = () => {
      const heightDifference = window.innerHeight - viewport.height;
      setKeyboardOpen(heightDifference > 120);
    };

    handleViewportChange();
    viewport.addEventListener('resize', handleViewportChange);
    viewport.addEventListener('scroll', handleViewportChange);

    return () => {
      viewport.removeEventListener('resize', handleViewportChange);
      viewport.removeEventListener('scroll', handleViewportChange);
    };
  }, []);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [prompt]);

  useEffect(() => {
    if (!loading) return undefined;

    setLoadingStory((currentStory) => getRandomLoadingStory(currentStory));
    const timer = window.setInterval(() => {
      setLoadingStory((currentStory) => getRandomLoadingStory(currentStory));
    }, 1800);

    return () => window.clearInterval(timer);
  }, [loading]);

  const handlePromptInput = (e) => {
    setPrompt(e.target.value);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setPlaylistUrl('');
    setSoundtrackUrl('');
    setSongs([]);

    try {
      const body = { prompt };
      if (mode === 'login') {
        body.access_token = accessToken;
        body.refresh_token = refreshToken;
      }

      const res = await axios.post(`${BACKEND}/generate_playlist`, body);
      const nextPlaylistUrl = res.data.playlist_url;
      const nextSoundtrackUrl = getLocalSoundtrackUrl(res.data.soundtrack_slug)
        || normalizeSoundtrackUrl(res.data.soundtrack_url);
      const nextSongs = res.data.songs_added || [];
      const nextPlaylistName = res.data.playlist_name || 'Your Soundtrack';

      setPlaylistUrl(nextPlaylistUrl);
      setSoundtrackUrl(nextSoundtrackUrl);
      showSoundtrackPageInAddressBar(nextSoundtrackUrl);
      setSongs(nextSongs);
      setPlaylistName(nextPlaylistName);
      setGuestMode(res.data.guest_mode);

      const historyItem = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        playlistName: nextPlaylistName,
        prompt: prompt.trim(),
        playlistUrl: nextPlaylistUrl,
        soundtrackUrl: nextSoundtrackUrl,
        songs: nextSongs,
        trackCount: nextSongs.length,
        createdAt: new Date().toISOString()
      };

      setSoundtrackHistory((currentHistory) => {
        const nextHistory = [
          historyItem,
          ...currentHistory.filter((item) => (
            item.playlistUrl !== historyItem.playlistUrl
            && (!historyItem.soundtrackUrl || item.soundtrackUrl !== historyItem.soundtrackUrl)
          ))
        ].slice(0, HISTORY_LIMIT);
        writeSoundtrackHistory(nextHistory);
        return nextHistory;
      });
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || '';
      if (message.toLowerCase().includes('token expired') || message.toLowerCase().includes('spotify auth error')) {
        setError('Your Spotify session expired. Please log in again.');
        setMode(isTestRoute ? null : 'guest');
        setAccessToken('');
        setRefreshToken('');
        localStorage.removeItem('spotify_access_token');
        localStorage.removeItem('spotify_refresh_token');
        localStorage.removeItem('spotify_token_timestamp');
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
    setSoundtrackUrl('');
    setSongs([]);
    setPrompt('');
    setError('');
    setShareStatus('');
    if (window.location.pathname.startsWith('/s/')) {
      window.history.replaceState({}, document.title, '/');
    }
  };

  const handleOpenHistoryItem = (item) => {
    const nextSoundtrackUrl = item.soundtrackUrl || '';
    setPlaylistUrl(item.playlistUrl);
    setSoundtrackUrl(nextSoundtrackUrl);
    showSoundtrackPageInAddressBar(nextSoundtrackUrl);
    setPlaylistName(item.playlistName);
    setSongs(item.songs || []);
    setPrompt(item.prompt || '');
    setGuestMode(true);
    setError('');
    setShareStatus('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleRemoveHistoryItem = (itemId) => {
    setSoundtrackHistory((currentHistory) => {
      const nextHistory = currentHistory.filter((item) => item.id !== itemId);
      writeSoundtrackHistory(nextHistory);
      return nextHistory;
    });
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

  const handleShare = async () => {
    let shareTargetUrl = getCurrentSoundtrackPageUrl() || soundtrackUrl;
    if (!shareTargetUrl) {
      if (!playlistName || !prompt.trim() || songs.length === 0) {
        setShareStatus('Make a new soundtrack first');
        return;
      }

      setCreatingShareLink(true);
      setShareStatus('Creating share link');
      try {
        const res = await axios.post(`${BACKEND}/soundtracks`, {
          prompt: prompt.trim(),
          playlist_name: playlistName,
          songs,
          spotify_url: playlistUrl || null
        });
        shareTargetUrl = getLocalSoundtrackUrl(res.data.soundtrack_slug)
          || normalizeSoundtrackUrl(res.data.soundtrack_url);

        if (!shareTargetUrl) {
          setShareStatus('Could not create link');
          return;
        }

        setSoundtrackUrl(shareTargetUrl);
        showSoundtrackPageInAddressBar(shareTargetUrl);
        setSoundtrackHistory((currentHistory) => {
          const nextHistory = currentHistory.map((item) => (
            item.playlistUrl === playlistUrl
              ? { ...item, soundtrackUrl: shareTargetUrl }
              : item
          ));
          writeSoundtrackHistory(nextHistory);
          return nextHistory;
        });
      } catch {
        setShareStatus('Could not create link');
        return;
      } finally {
        setCreatingShareLink(false);
      }
    }

    const shareTitle = playlistName || 'Butterfly soundtrack';
    const shareText = prompt.trim()
      ? `Butterfly made me a soundtrack for: ${prompt.trim()}`
      : 'Butterfly made me a soundtrack.';
    const shareData = {
      title: shareTitle,
      text: shareText,
      url: shareTargetUrl
    };
    const failedShareStatus = 'Share from browser menu';

    try {
      if (navigator.share && navigator.canShare?.(shareData)) {
        await navigator.share(shareData);
        setShareStatus('Shared');
      } else if (navigator.share) {
        await navigator.share({ title: shareTitle, text: shareText, url: shareTargetUrl });
        setShareStatus('Shared');
      } else {
        const copied = await copyTextToClipboard(shareTargetUrl);
        setShareStatus(copied ? 'Link copied' : failedShareStatus);
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      const copied = await copyTextToClipboard(shareTargetUrl);
      setShareStatus(copied ? 'Link copied' : failedShareStatus);
    }
  };

  const hasPrompt = prompt.trim().length > 0;
  const appClasses = `app-shell font-body text-sage-900${keyboardOpen ? ' keyboard-open' : ''}${loading ? ' is-loading' : ''}`;
  const promptSummary = prompt.trim();
  const hasResult = Boolean(playlistUrl || soundtrackUrl);
  const currentHistoryItem = soundtrackHistory.find((item) => (
    item.playlistUrl === playlistUrl || (soundtrackUrl && item.soundtrackUrl === soundtrackUrl)
  ));
  const displayedTrackCount = songs.length || currentHistoryItem?.trackCount || 0;
  const displayedTrackCountLabel = displayedTrackCount === 1 ? '1 song' : `${displayedTrackCount} songs`;
  const hasTrackRows = songs.length > 0;
  const visibleHistory = soundtrackHistory.slice(0, 4);
  const getHistoryTrackLabel = (trackCount) => trackCount === 1 ? '1 song' : `${trackCount} songs`;

  return (
    <div className={appClasses}>
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

        {loadingSavedSoundtrack && !hasResult && (
          <section className="creating-state" role="status" aria-live="polite">
            <div className="pulse-mark">
              <img src="/butterfly-logo.png" alt="" className="h-8 w-8" />
            </div>
            <div>
              <p className="creating-title">Opening soundtrack</p>
              <p className="creating-copy">Loading the saved tracklist.</p>
            </div>
          </section>
        )}

        {mode !== null && !hasResult && !loadingSavedSoundtrack && (
          <form onSubmit={handleSubmit} className="composer-screen">
            <section className="composer-panel" aria-busy={loading}>
              <p className="eyebrow">Butterfly</p>
              <label htmlFor="playlist-prompt" className="composer-label">
                What should your soundtrack feel like?
              </label>

              <textarea
                ref={textareaRef}
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

            {visibleHistory.length > 0 && !loading && (
              <section className="history-section" aria-labelledby="history-title">
                <div className="history-heading">
                  <h2 id="history-title">Recent soundtracks</h2>
                  <span>{soundtrackHistory.length}</span>
                </div>

                <div className="history-list">
                  {visibleHistory.map((item) => (
                    <div key={item.id} className="history-row">
                      <button
                        type="button"
                        onClick={() => handleOpenHistoryItem(item)}
                        className="history-item"
                        aria-label={`Open ${item.playlistName} result`}
                      >
                        <div className="history-copy">
                          <span className="history-title">{item.playlistName}</span>
                          <span className="history-prompt">{item.prompt}</span>
                        </div>
                        <div className="history-meta">
                          <span>{getHistoryTrackLabel(item.trackCount)}</span>
                          <span>{formatHistoryDate(item.createdAt)}</span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveHistoryItem(item.id)}
                        className="history-remove"
                        aria-label={`Remove ${item.playlistName} from history`}
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24">
                          <path d="M10 11v6" />
                          <path d="M14 11v6" />
                          <path d="M5 7h14" />
                          <path d="M8 7l1-3h6l1 3" />
                          <path d="M7 7l1 14h8l1-14" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {loading && (
              <section className="creating-state" role="status" aria-live="polite">
                <div className="pulse-mark">
                  <img src="/butterfly-logo.png" alt="" className="h-8 w-8" />
                </div>
                <div>
                  <p className="creating-title">Creating your soundtrack</p>
                  <p className="creating-copy">{loadingStory}</p>
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

        {hasResult && (
          <section className="result-screen">
            <div className="playlist-hero">
              <div className="playlist-kicker">
                <p className="eyebrow">Your soundtrack</p>
                {displayedTrackCount > 0 && <span className="track-count">{displayedTrackCountLabel}</span>}
              </div>
              <h1 className="playlist-title">{playlistName || 'Your Soundtrack'}</h1>
              {promptSummary && (
                <p className="playlist-prompt">
                  Made for: {promptSummary}
                </p>
              )}
              {guestMode && (
                <p className="playlist-note">
                  Follow it on Spotify to save it to your library.
                </p>
              )}
            </div>

            {hasTrackRows ? (
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
            ) : (
              <div className="saved-result-note">
                <p>This soundtrack was saved before track details were stored on device.</p>
              </div>
            )}

            <div className="bottom-action result-actions">
              {playlistUrl && (
                <a
                  href={playlistUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="primary-button"
                >
                  <span className="spotify-dot" aria-hidden="true" />
                  Listen on Spotify
                </a>
              )}
              <button
                type="button"
                onClick={handleShare}
                disabled={creatingShareLink}
                className="quiet-button share-button"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M12 3v12" />
                  <path d="M7 8l5-5 5 5" />
                  <path d="M5 13v6h14v-6" />
                </svg>
                {creatingShareLink ? 'Creating share link' : 'Share soundtrack'}
              </button>
              {shareStatus && (
                <p className="share-status" role="status" aria-live="polite">
                  {shareStatus}
                </p>
              )}
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
