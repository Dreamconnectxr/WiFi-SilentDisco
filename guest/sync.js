(() => {
  const form = document.getElementById('connection-form');
  const player = document.getElementById('player');
  const statusEl = document.getElementById('status');
  const latencyEl = document.getElementById('latency');
  const targetEl = document.getElementById('target-latency');
  const rateEl = document.getElementById('playback-rate');
  const clockEl = document.getElementById('clock-offset');

  let hlsInstance = null;
  let syncTimer = null;
  let targetLatency = 2;
  let clockOffsetMs = 0;

  async function fetchSyncMetadata() {
    try {
      const response = await fetch('/api/time', { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`Time API ${response.status}`);
      }
      const payload = await response.json();
      if (typeof payload.epoch === 'number') {
        const now = Date.now();
        clockOffsetMs = payload.epoch * 1000 - now;
        clockEl.textContent = clockOffsetMs.toFixed(0);
      }
      if (typeof payload.targetLatency === 'number') {
        targetLatency = payload.targetLatency;
        targetEl.textContent = targetLatency.toFixed(2);
      }
    } catch (error) {
      console.warn('Failed to fetch sync metadata', error);
      statusEl.textContent = 'Time sync unavailable';
    }
  }

  function cleanupPlayer() {
    if (hlsInstance) {
      hlsInstance.destroy();
      hlsInstance = null;
    }
    if (syncTimer) {
      clearInterval(syncTimer);
      syncTimer = null;
    }
    player.pause();
    player.removeAttribute('src');
    player.load();
  }

  function updateStatus(message) {
    statusEl.textContent = message;
  }

  function startSyncLoop() {
    if (syncTimer) {
      clearInterval(syncTimer);
    }
    syncTimer = setInterval(() => {
      let latency = null;
      if (hlsInstance && typeof hlsInstance.latency === 'number' && !Number.isNaN(hlsInstance.latency)) {
        latency = hlsInstance.latency;
      }
      if (latency !== null) {
        latencyEl.textContent = latency.toFixed(2);
        const diff = latency - targetLatency;
        const absDiff = Math.abs(diff);
        if (absDiff > 0.35 && !Number.isNaN(player.currentTime)) {
          const adjustment = Math.max(-0.6, Math.min(0.6, diff * 0.5));
          player.currentTime -= adjustment;
        }
        const rate = Math.max(0.94, Math.min(1.06, 1 - diff * 0.08));
        player.playbackRate = rate;
        rateEl.textContent = rate.toFixed(3);
      } else {
        latencyEl.textContent = '–';
        player.playbackRate = 1.0;
        rateEl.textContent = '1.000';
      }
    }, 1200);
  }

  async function attachStream(source) {
    cleanupPlayer();
    await fetchSyncMetadata();

    if (player.canPlayType('application/vnd.apple.mpegurl')) {
      player.src = source;
      const play = () => player.play().catch(() => updateStatus('Tap play to start audio'));
      player.addEventListener('loadedmetadata', () => {
        play();
      }, { once: true });
      await play();
      startSyncLoop();
      return;
    }

    if (window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        lowLatencyMode: true,
        liveSyncDuration: targetLatency,
        liveMaxLatencyDuration: Math.max(targetLatency + 1, 3),
      });
      hls.loadSource(source);
      hls.attachMedia(player);
      let started = false;
      const ensurePlayback = () => {
        if (started) return;
        started = true;
        player.play().then(() => {
          updateStatus('Playing');
        }).catch(() => updateStatus('Tap play to start audio'));
      };
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        updateStatus('Buffering…');
        ensurePlayback();
      });
      hls.on(window.Hls.Events.LEVEL_UPDATED, () => {
        ensurePlayback();
      });
      hls.on(window.Hls.Events.ERROR, (_, data) => {
        console.error('HLS error', data);
        if (data?.fatal) {
          updateStatus('Fatal error – reconnecting');
          attachStream(source).catch((err) => console.error(err));
        }
      });
      hlsInstance = hls;
      startSyncLoop();
      return;
    }

    updateStatus('HLS is not supported in this browser');
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const host = formData.get('host');
    const port = formData.get('llhls-port');
    const app = formData.get('app');
    const stream = formData.get('stream');

    if (!host || !port || !app || !stream) {
      updateStatus('Fill in all fields');
      return;
    }

    const playlist = `http://${host}:${port}/${app}/${stream}/playlist.m3u8`;
    updateStatus('Connecting…');
    attachStream(playlist).catch((error) => {
      console.error(error);
      updateStatus('Failed to attach stream');
    });
  });

  window.addEventListener('beforeunload', () => {
    cleanupPlayer();
  });
})();
