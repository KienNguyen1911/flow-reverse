"""In-page fetch hook injected into the Flow tab (video bridge)."""

from __future__ import annotations

from .constants import VIDEO_DECOY_RPCS


def _submit_rpc_checks() -> str:
    """``s.indexOf('rpcids=<id>') >= 0 ||`` for every decoy RPC, in declared order."""
    return " ||\n".join(f"      s.indexOf('rpcids={rpcid}') >= 0" for rpcid in VIDEO_DECOY_RPCS)


# In-page fetch hook for Video Bridge Mode:
# - Blocks the app's own submit request when window.__blockVideoGen == true (0 credit on the
#   decoy). Every submit RPC is blocked, because which one the app fires depends on the
#   composer state (frames only / first+last / ingredients / video reference).
# - Passively captures maseQ upload responses so starting_frame_media_id is read from JSON.
VIDEO_HOOK_JS = (
    r"""
(() => {
  window.__isVideoSubmit = function (u) {
    const s = String(u || '');
    if (s.indexOf('/data/batchexecute?') < 0) return false;
    return (
"""
    + _submit_rpc_checks()
    + r"""
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

  if (!window.__videoHook || (window.__videoHook.v || 0) < 4) {
    window.__videoHook = {v: 4, cap: null, blocked: false, lastUpload: null};
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
          return Promise.reject(new Error('bridge-blocked-video-submit'));
        }
        const body = String((init && init.body) || '');
        window.__videoHook.cap = {url: String(url), body: body, bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__videoHook.blocked = true;
        return Promise.reject(new Error('bridge-blocked-video-submit'));
      }

      return prevFetch.apply(this, arguments);
    };
  }
  window.__videoHook.cap = null;
  window.__videoHook.blocked = false;
  window.__blockVideoGen = true;
  return {installed: true, v: window.__videoHook.v, rpcs: """
    + repr(list(VIDEO_DECOY_RPCS))
    + r"""};
})()
"""
)

