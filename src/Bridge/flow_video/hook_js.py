"""In-page fetch hook injected into the Flow tab (video bridge)."""

from __future__ import annotations

# In-page fetch hook for Video Bridge Mode:
# - Blocks app's own eb1hJf (and ogiZ0b) when window.__blockVideoGen == true (0 credit on decoy).
# - Passively captures maseQ upload responses so starting_frame_media_id is read from JSON.
VIDEO_HOOK_JS = r"""
(() => {
  window.__isVideoSubmit = u => {
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
      s.indexOf('rpcids=p0UkFb') >= 0 ||
      s.indexOf('rpcids=ogiZ0b') >= 0
    );
  };
  const isMaseQ = u => {
    const s = String(u || '');
    return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=maseQ') >= 0;
  };
  const isOurs = h => {
    try { return !!(h && (h['x-harness-ours'] || (h.get && h.get('x-harness-ours')))); }
    catch (e) { return false; }
  };

  if (!window.__videoHook || (window.__videoHook.v || 0) < 3) {
    window.__videoHook = {v: 3, cap: null, blocked: false, lastUpload: null};
    const prevFetch = window.__origFetchForVideo || window.fetch;
    window.__origFetchForVideo = prevFetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      const ours = isOurs(init && init.headers);

      if (isMaseQ(url) && !ours) {
        const up = {url: String(url), resp: '', ready: false, status: 0, ts: Date.now()};
        window.__videoHook.lastUpload = up;
        return prevFetch.apply(this, arguments).then(r => {
          up.status = r.status;
          try {
            r.clone().text().then(t => { up.resp = t; up.ready = true; }).catch(() => { up.ready = true; });
          } catch (e) { up.ready = true; }
          return r;
        });
      }

      const checkSub = window.__isVideoSubmit || (() => false);
      if (checkSub(url) && window.__blockVideoGen && !ours) {
        if (typeof input !== 'string' && input && typeof input.text === 'function') {
          const cap = {url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request'};
          window.__videoHook.cap = cap;
          input.text().then(t => {
            cap.body = t;
            cap.bodyReady = true;
            window.__videoHook.blocked = true;
          }).catch(e => {
            cap.readErr = String(e);
            cap.bodyReady = true;
          });
          return Promise.reject(new Error('bridge-blocked-eb1hJf'));
        }
        const body = String((init && init.body) || '');
        window.__videoHook.cap = {url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__videoHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-eb1hJf'));
      }

      return prevFetch.apply(this, arguments);
    };
  }
  window.__videoHook.cap = null;
  window.__videoHook.blocked = false;
  window.__blockVideoGen = true;
  return {installed: true, v: window.__videoHook.v};
})()
"""
