"""In-page fetch hook injected into the Flow tab (image bridge)."""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Page hook (proven shape from the E-series experiments; idempotent)
# --------------------------------------------------------------------------- #

HOOK_JS = r"""
(() => {
  const isOgi = u => { const s = String(u || ''); return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=ogiZ0b') >= 0; };
  const isVideoSubmit = u => {
    const s = String(u || '');
    if (s.indexOf('/data/batchexecute?') < 0) return false;
    return (
      s.indexOf('rpcids=eb1hJf') >= 0 ||
      s.indexOf('rpcids=MZZa6b') >= 0 ||
      s.indexOf('rpcids=YhhmEf') >= 0 ||
      s.indexOf('rpcids=nprQif') >= 0 ||
      s.indexOf('rpcids=fZytfe') >= 0 ||
      s.indexOf('rpcids=jIps6') >= 0 ||
      s.indexOf('rpcids=IJhj9c') >= 0 ||
      s.indexOf('rpcids=p0UkFb') >= 0
    );
  };
  const isOurs = h => { try { return !!(h && (h['x-harness-ours'] || (h.get && h.get('x-harness-ours')))); } catch (e) { return false; } };
  if (!window.__flowHook) {
    window.__flowHook = {v: 3, cap: null, blocked: false};
    const prevFetch = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      const ours = isOurs(init && init.headers);

      // Safety guard: Never allow accidental video generation during image bridge mode (saves 12 credits)
      if (isVideoSubmit(url) && window.__blockOgi && !ours) {
        console.warn('[bridge] Blocked unexpected video submit during image generation mode');
        return Promise.reject(new Error('bridge-blocked-unexpected-video-submit'));
      }

      if (!isOgi(url) || !window.__blockOgi) return prevFetch(input, init);
      if (typeof input !== 'string' && input && typeof input.text === 'function') {
        if (!ours) {
          const cap = {url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request'};
          window.__flowHook.cap = cap;
          input.text().then(t => { cap.body = t; cap.bodyReady = true; window.__flowHook.blocked = true; })
            .catch(e => { cap.readErr = String(e); cap.bodyReady = true; });
          return Promise.reject(new Error('bridge-blocked-ogiz0b'));
        }
        return prevFetch(input, init);
      }
      const body = String((init && init.body) || '');
      if (!ours) {
        window.__flowHook.cap = {url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__flowHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-ogiz0b'));
      }
      return prevFetch(input, init);
    };
  }
  window.__flowHook.cap = null;
  window.__flowHook.blocked = false;
  window.__blockOgi = true;
  return {installed: true};
})()
"""
