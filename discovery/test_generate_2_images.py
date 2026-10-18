"""End-to-end test: generate N images (default 2) via the proven in-page bridge flow.

What it does (per image), reusing the exact mechanism validated in experiments E7/E8:
  1. Attach to the running CloakBrowser via CDP (browser-harness, port 9222).
  2. Install an idempotent fetch hook in the page:
       - blocks the app's own ogiZ0b request (so it costs 0 credit),
       - captures its URL + body (which carries the fresh reCAPTCHA token).
  3. SPA-navigate to the target project, type the prompt, click Generate (the app
     mints a fresh token internally; its own ogiZ0b is blocked by our hook).
  4. Read the captured body -> token / at / _reqid; build OUR OWN ogiZ0b body
     (builder validated in E8: uppercase UUIDs, _reqid = app_reqid + 100000).
  5. Fire it in-page within ~100 ms; long-poll ~18-24 s.
  6. Parse the response (double JSON decode), extract the signed CDN URL and
     download the image (with retries).

COST WARNING: every ACCEPTED generation uses ~1 credit. Rejected requests cost 0.
Use --dry-run to validate the whole capture+build pipeline without firing (0 credit).

Usage:
  python discovery/test_generate_2_images.py                 # real run: 2 images (~2 credit max)
  python discovery/test_generate_2_images.py --dry-run       # capture+build only, NO fire, 0 credit
  python discovery/test_generate_2_images.py --project <uuid> --prompts "p1|p2" --out out
  python discovery/test_generate_2_images.py --yes           # skip confirmation prompt

Requirements:
  - CloakBrowser running with --remote-debugging-port=9222 (src/BrowserHost/launch_profile.py)
  - The active tab logged in on https://flow.google.com
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent  # project root (script sits in discovery/)
CDP_URL = "http://127.0.0.1:9222"
ENV = dict(os.environ, BU_CDP_URL=CDP_URL)

DEFAULT_PROJECT = "3b368b0d-2e22-4ba0-9f8e-c17e698ddcb9"  # test project (teapots)
DEFAULT_PROMPTS = [
    "a red apple on a white ceramic plate, studio light",
    "a yellow rubber duck floating on calm water, sunny day",
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Page hook: idempotent fetch wrapper around the proven E8 hook.
# Blocks app's ogiZ0b (capture url+body via input.text()) and lets our own
# request through when it carries the x-harness-ours bypass header.
# ---------------------------------------------------------------------------
HOOK_JS = """
(() => {
  const isOgi = u => { const s = String(u || ''); return s.indexOf('/data/batchexecute?') >= 0 && s.indexOf('rpcids=ogiZ0b') >= 0; };
  if (!window.__hTestHook) {
    window.__ogHook = window.__ogHook || {cap: null, blocked: false};
    const prevFetch = window.fetch;
    window.fetch = function(input, init) {
      let url = '';
      try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) {}
      if (!isOgi(url) || !window.__blockOgi) return prevFetch(input, init);
      const h = (init && init.headers) || {};
      let ours = false;
      try { ours = !!(h['x-harness-ours'] || (h.get && h.get('x-harness-ours'))); } catch (e) {}
      if (typeof input !== 'string' && input && typeof input.text === 'function') {
        const cap = {url: String(url), body: '', bodyReady: false, ts: Date.now(), via: 'fetch-request'};
        window.__ogHook.cap = cap;
        if (!ours) {
          input.text().then(t => { cap.body = t; cap.bodyReady = true; window.__ogHook.blocked = true; })
            .catch(e => { cap.readErr = String(e); cap.bodyReady = true; });
          return Promise.reject(new Error('harness-blocked-ogiz0b'));
        }
      } else {
        const cap = {url: String(url), body: String((init && init.body) || ''), bodyReady: true, ts: Date.now(), via: 'fetch-init'};
        window.__ogHook.cap = cap;
        if (!ours) {
          window.__ogHook.blocked = true;
          return Promise.reject(new Error('harness-blocked-ogiz0b'));
        }
      }
      return prevFetch(input, init);
    };
    window.__hTestHook = true;
  }
  window.__ogHook = window.__ogHook || {cap: null, blocked: false};
  window.__ogHook.cap = null;
  window.__ogHook.blocked = false;
  window.__blockOgi = true;
  return {ok: true, installed: true};
})()
"""

# ---------------------------------------------------------------------------
# Harness program (runs inside browser-harness, one per image).
# Placeholders __*_PY__ are replaced with valid Python literals in bare
# assignment contexts (safe injection pattern proven in E8).
# ---------------------------------------------------------------------------
HARNESS_TMPL = r'''
import time, json, re, random, uuid, os
from urllib.parse import parse_qs, quote, unquote_plus

PROMPT = __PROMPT_PY__
PROJECT = __PROJECT_PY__
OUT_DIR = __OUTDIR_PY__
IDX = __IDX_PY__
DO_FIRE = __DOFIRE_PY__
HK_JS = __HOOKJS_PY__

def enc(s):
    return quote(s, safe="!'()*-._~")

def write(fn, text):
    with open(os.path.join(OUT_DIR, fn), 'w', encoding='utf-8') as f:
        f.write(text)

os.makedirs(OUT_DIR, exist_ok=True)
print('IMG_IDX:', IDX, '| PROMPT:', PROMPT)
print('HOOK:', json.dumps(js(HK_JS)))

# --- SPA reset: home -> target project (fresh composer + correct project) ---
js("(() => { try { history.pushState({}, '', '/'); window.dispatchEvent(new PopStateEvent('popstate')); } catch (e) {} return true; })()")
time.sleep(3)
js("(() => { try { history.pushState({}, '', '/project/' + " + json.dumps(PROJECT) + "); window.dispatchEvent(new PopStateEvent('popstate')); } catch (e) {} return true; })()")
time.sleep(4)
pi = page_info() or {}
print('PAGE:', json.dumps(pi))
if 'flow.google.com' not in (pi.get('url') or ''):
    print('ERROR: active tab is not flow.google.com ->', pi.get('url'))
    raise SystemExit(10)

# --- composer: poll until present ---
pos = None
for _ in range(16):
    pos = js("(() => { const ed = document.querySelector('div.ProseMirror'); if (!ed) return {found: false}; const r = ed.getBoundingClientRect(); return {found: true, x: Math.round(r.x + 24), y: Math.round(r.y + r.height / 2)}; })()")
    if isinstance(pos, dict) and pos.get('found'):
        break
    time.sleep(0.5)
print('ED:', json.dumps(pos))
if not (isinstance(pos, dict) and pos.get('found')):
    print('ERROR: prompt composer not found')
    raise SystemExit(11)

# type prompt with retries (the app may re-render and drop text right after SPA nav)
typed = False
for attempt in range(4):
    pos = js("(() => { const ed = document.querySelector('div.ProseMirror'); if (!ed) return {found: false}; const r = ed.getBoundingClientRect(); return {found: true, x: Math.round(r.x + 24), y: Math.round(r.y + r.height / 2)}; })()")
    if not (isinstance(pos, dict) and pos.get('found')):
        print('TYPE_TRY %d: composer missing' % attempt)
        time.sleep(1.0)
        continue
    click_at_xy(pos['x'], pos['y'])
    time.sleep(0.5)
    act = js("(() => { const a = document.activeElement; return a ? (a.tagName + '.' + String(a.className || '').slice(0, 60)) : 'none'; })()")
    print('TYPE_TRY %d: active=%s' % (attempt, act))
    try:
        js("(() => { try { document.execCommand('selectAll'); } catch (e) {} return true; })()")
    except Exception:
        pass
    cdp('Input.insertText', text=PROMPT)
    time.sleep(0.9)
    txt = js("(() => { try { return (document.querySelector('div.ProseMirror').innerText || '').slice(0, 140); } catch (e) { return ''; } })()")
    print('COMPOSER[%d]:' % attempt, json.dumps(txt))
    if PROMPT[:20].lower() in (txt or '').lower():
        typed = True
        break
    try:
        cdp('Runtime.evaluate', expression="(() => { try { const ev = new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}); document.dispatchEvent(ev); } catch (x) {} return true; })()")
    except Exception:
        pass
    time.sleep(1.0)
if not typed:
    print('ERROR: could not type the prompt into the composer after 4 attempts')
    raise SystemExit(11)

# --- generate button: poll until enabled ---
gb = None
for _ in range(16):
    gb = js("(() => { const b = document.querySelector('button.generate-icon-button'); if (!b) return {found: false}; const r = b.getBoundingClientRect(); return {found: true, disabled: !!b.disabled, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}; })()")
    if isinstance(gb, dict) and gb.get('found') and not gb.get('disabled'):
        break
    time.sleep(0.5)
print('GENBTN:', json.dumps(gb))
if not (isinstance(gb, dict) and gb.get('found') and not gb.get('disabled')):
    print('ERROR: generate button not found/enabled')
    raise SystemExit(12)
click_at_xy(gb['x'], gb['y'])
click_ts = int(time.time() * 1000)
print('CLICKED:', click_ts)

# --- capture the app's blocked ogiZ0b attempt ---
cap = None
for i in range(130):
    time.sleep(0.15)
    st = cdp('Runtime.evaluate', expression="JSON.stringify(window.__ogHook && window.__ogHook.cap && window.__ogHook.cap.bodyReady ? {url: window.__ogHook.cap.url, body: window.__ogHook.cap.body, ts: window.__ogHook.cap.ts, via: window.__ogHook.cap.via} : null)", returnByValue=True)
    val = (st.get('result') or {}).get('value')
    try:
        j = json.loads(val) if val else None
    except Exception:
        j = None
    if j and len(j.get('body') or '') > 100:
        cap = j
        break
if not cap:
    print('ERROR: no ogiZ0b capture within ~20s (app request not observed)')
    raise SystemExit(13)
print('CAPTURE via=%s ts=%s len=%d' % (cap.get('via'), cap.get('ts'), len(cap['body'])))
app_body = cap['body']
app_url = cap.get('url') or ''
write('image_%d_app_request_body.txt' % IDX, app_body)

# --- parse capture: token / at / reqid ---
tok = ''
at_param = ''
try:
    qs2 = parse_qs(app_body, keep_blank_values=True)
    obj2 = json.loads(qs2.get('f.req', [''])[0])
    app_args2 = json.loads(obj2[0][0][1])
    tok = app_args2[1][0][7][10][0]
    at_param = qs2.get('at', [''])[0]
except Exception as e:
    print('WARN: structured parse failed (%r) -> regex fallback' % (e,))
if not tok:
    mmt = re.search(r'0cAFcWeA[A-Za-z0-9_\-]{400,}', app_body)
    tok = mmt.group(0) if mmt else ''
if not at_param:
    mmat = re.search(r'(?:^|&)at=([^&]+)', app_body)
    at_param = unquote_plus(mmat.group(1)) if mmat else ''
mm = re.search(r'([?&]_reqid=)(\d+)', app_url)
old_reqid = int(mm.group(2)) if mm else None
new_reqid = (old_reqid + 100000) if old_reqid is not None else 990001
print('TOKEN len=%d prefix=%s | at len=%d | app_reqid=%s' % (len(tok), tok[:16], len(at_param), old_reqid))
if not (len(tok) > 2000 and tok.startswith('0cAFcWeA')):
    print('ERROR: token sanity failed')
    raise SystemExit(14)
if len(at_param) < 10:
    print('ERROR: at param missing')
    raise SystemExit(15)

# --- build OUR OWN body (builder proven in E8) ---
# seed must fit a SIGNED int32: the app's own seeds are always < 2^31 and a
# seed > 2^31-1 makes the server answer [3] INVALID_ARGUMENT (observed on the
# 2026-10-18 18:49 fire; E8 had passed only by lucky draw).
seed = random.randint(1, 2147483647)
u1 = str(uuid.uuid4()).upper()
u2 = str(uuid.uuid4()).upper()
gen = str(uuid.uuid4()).upper()
ref = [None, 22, None, None, None, PROJECT, None, None, None, None, [tok, 1]]
spec = [None, None, None, seed, 3, 'BELUGA', None, ref, [[[PROMPT]]], None, None, None, u1, u2]
args = [None, [spec], 1, ref, [gen]]
f_req_new = json.dumps([[['ogiZ0b', json.dumps(args, separators=(',', ':'), ensure_ascii=False), None, 'generic']]], separators=(',', ':'), ensure_ascii=False)
body_new = 'f.req=' + enc(f_req_new) + '&at=' + enc(at_param) + '&'
write('image_%d_our_request_body.txt' % IDX, body_new)
write('image_%d_our_args.pretty.json' % IDX, json.dumps(args, ensure_ascii=False, indent=1))
print('OUR_BODY len=%d | seed=%d | gen=%s' % (len(body_new), seed, gen))

meta = {
    'index': IDX, 'prompt': PROMPT, 'project': PROJECT, 'seed': seed,
    'generation_id': gen, 'uuid1': u1, 'uuid2': u2,
    'token_len': len(tok), 'app_reqid': old_reqid, 'our_reqid': new_reqid,
    'app_body_len': len(app_body), 'our_body_len': len(body_new),
    'capture_ts': cap.get('ts'), 'capture_via': cap.get('via'), 'click_ts': click_ts,
}
write('image_%d_meta.json' % IDX, json.dumps(meta, ensure_ascii=False, indent=1))

if not DO_FIRE:
    print('DRY_RUN: capture + build OK - NOT firing (0 credit)')
    print('HARNESS DONE')
    raise SystemExit(0)

# --- fire OUR request ---
new_url = re.sub(r'([?&]_reqid=)\d+', lambda m2: m2.group(1) + str(new_reqid), app_url)
fire_js = ("(async () => { try { window.__fireTs = Date.now(); const r = await fetch(" + json.dumps(new_url) + ", {method: 'POST', credentials: 'include', headers: {'content-type': 'application/x-www-form-urlencoded;charset=utf-8', 'x-same-domain': '1', 'x-harness-ours': '1'}, body: " + json.dumps(body_new) + "}); const t = await r.text(); window.__ogiState = {state: 'done', status: r.status, len: t.length, text: t}; return {ok: true, status: r.status, len: t.length}; } catch (e) { window.__ogiState = {state: 'error', error: String(e)}; return {ok: false, error: String(e)}; } })()")
js("window.__ogiState = {state: 'pending'}")
fire = cdp('Runtime.evaluate', expression=fire_js, awaitPromise=False, returnByValue=True)
print('FIRE:', json.dumps(fire)[:220])
fts = js("window.__fireTs || 0")
try:
    print('GAP capture->fire: %d ms' % (int(fts) - int(cap.get('ts') or fts)))
except Exception:
    pass

done = False
for i in range(25):
    time.sleep(3)
    st2 = cdp('Runtime.evaluate', expression="JSON.stringify(window.__ogiState || {state: 'none'})", returnByValue=True)
    v2 = (st2.get('result') or {}).get('value')
    try:
        j2 = json.loads(v2) if v2 else None
    except Exception:
        j2 = None
    print('POLL %d:' % i, str(v2)[:130])
    if j2 and j2.get('state') in ('done', 'error'):
        done = True
        break
if done:
    f2 = cdp('Runtime.evaluate', expression="(window.__ogiState && window.__ogiState.text) || ''", returnByValue=True)
    txt2 = (f2.get('result') or {}).get('value') or ''
    write('image_%d_response.txt' % IDX, txt2)
    print('RESP_SAVED len=%d' % len(txt2))
else:
    print('ERROR: response poll timeout (~75s)')
print('HARNESS DONE')
'''


def harness_call(program, timeout=260):
    r = subprocess.run("browser-harness", shell=True, input=program, capture_output=True,
                       text=True, env=ENV, timeout=timeout)
    out = r.stdout or ""
    if r.stderr:
        out += "\n[STDERR]\n" + r.stderr[-1200:]
    return out


def find_urls(o, acc=None):
    if acc is None:
        acc = []
    if isinstance(o, str):
        if o.startswith("https://flow-content.google/image/"):
            acc.append(o)
    elif isinstance(o, list):
        for x in o:
            find_urls(x, acc)
    elif isinstance(o, dict):
        for x in o.values():
            find_urls(x, acc)
    return acc


def parse_response(txt):
    payload = None
    for line in txt.splitlines():
        ls = line.strip()
        if ls.startswith('[["wrb.fr"'):
            payload = ls
            break
    if payload is None:
        return {"ok": False, "reason": "no_wrbfr_payload"}
    try:
        arr = json.loads(payload)
    except Exception as e:
        return {"ok": False, "reason": "payload_json_error: %r" % (e,)}
    if not arr or not isinstance(arr[0], list):
        return {"ok": False, "reason": "unexpected_payload_shape"}
    row = arr[0]
    if len(row) >= 3 and row[2]:
        try:
            return {"ok": True, "data": json.loads(row[2])}
        except Exception as e:
            return {"ok": False, "reason": "inner_json_error: %r" % (e,)}
    detail = row[5] if len(row) > 5 else row
    return {"ok": False, "reason": "rpc_error",
            "detail": json.dumps(detail, ensure_ascii=False)[:600]}


def download(url, dest, attempts=4, delay=8):
    for a in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                d = resp.read()
                is_img = (d[:3] == b"\xff\xd8\xff" or d[:8] == b"\x89PNG\r\n\x1a\n"
                          or (d[:4] == b"RIFF" and d[8:12] == b"WEBP"))
                if is_img:
                    dest.write_bytes(d)
                    print("   download OK: %s (%d bytes)" % (dest.name, len(d)))
                    return True
                print("   download attempt %d: unexpected content (%s, %d bytes)"
                      % (a + 1, resp.headers.get("Content-Type"), len(d)))
        except urllib.error.HTTPError as e:
            print("   download attempt %d: HTTP %s" % (a + 1, e.code))
        except Exception as e:
            print("   download attempt %d: %r" % (a + 1, e))
        if a < attempts - 1:
            time.sleep(delay)
    return False


def slugify(p):
    s = re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_")
    return s[:40].strip("_") or "image"


def main():
    ap = argparse.ArgumentParser(description="Generate test images end-to-end (bridge flow).")
    ap.add_argument("--project", default=DEFAULT_PROJECT, help="target Flow project UUID")
    ap.add_argument("--prompts", default=None,
                    help='prompts separated by "|" (default: 2 sample prompts)')
    ap.add_argument("--out", default=None, help="output base directory (default: <root>/out)")
    ap.add_argument("--dry-run", action="store_true",
                    help="capture + build only, never fire (0 credit)")
    ap.add_argument("--yes", action="store_true", help="skip the credit confirmation prompt")
    args = ap.parse_args()

    prompts = ([p.strip() for p in args.prompts.split("|") if p.strip()]
               if args.prompts else list(DEFAULT_PROMPTS))
    project = args.project
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_base = pathlib.Path(args.out) if args.out else (ROOT / "out")
    run_dir = out_base / ("test_2images_" + ts)
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("RUN DIR :", run_dir)
    print("PROJECT :", project)
    print("PROMPTS :", prompts)
    print("MODE    :", "DRY-RUN (0 credit)" if args.dry_run
          else "REAL (each accepted image ~= 1 credit)")
    print("=" * 64)

    check = harness_call("import json\nprint('TAB:', json.dumps(page_info()))", timeout=60)
    print(check.strip()[:400])
    if "flow.google.com" not in check:
        print("!! WARNING: no flow.google.com tab visible via CDP. "
              "Make sure CloakBrowser is running (port 9222) and the Flow tab is active.")

    if not args.dry_run and not args.yes and sys.stdin.isatty():
        ans = input("Continue? (~%d credit if all succeed) [y/N] " % len(prompts))
        if ans.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1

    meta_all = {"run_ts": ts, "project": project, "cdp": CDP_URL,
                "dry_run": bool(args.dry_run), "images": []}

    for idx, prompt in enumerate(prompts, 1):
        print("\n" + "-" * 60)
        print("IMAGE %d/%d: %s" % (idx, len(prompts), prompt))
        t0 = time.time()
        program = (HARNESS_TMPL
                   .replace("__PROMPT_PY__", json.dumps(prompt))
                   .replace("__PROJECT_PY__", json.dumps(project))
                   .replace("__OUTDIR_PY__", json.dumps(str(run_dir).replace("\\", "/")))
                   .replace("__IDX_PY__", repr(idx))
                   .replace("__DOFIRE_PY__", repr(not args.dry_run))
                   .replace("__HOOKJS_PY__", json.dumps(HOOK_JS)))
        out = harness_call(program)
        (run_dir / ("image_%d_harness_output.txt" % idx)).write_text(out, encoding="utf-8")
        print(out.strip()[-2200:])

        entry = {"index": idx, "prompt": prompt}
        mf = run_dir / ("image_%d_meta.json" % idx)
        if mf.exists():
            try:
                entry.update(json.loads(mf.read_text(encoding="utf-8")))
            except Exception:
                pass

        if "HARNESS DONE" not in out:
            entry["status"] = "harness_failed"
            entry["harness_tail"] = out.strip()[-800:]
            meta_all["images"].append(entry)
            print(">> IMAGE %d: [FAIL] harness error (see log)" % idx)
            continue

        if args.dry_run:
            entry["status"] = "dry_run_ok"
            entry["elapsed_s"] = round(time.time() - t0, 1)
            meta_all["images"].append(entry)
            print(">> IMAGE %d: [DRY-OK] capture + build succeeded, not fired (0 credit)" % idx)
            continue

        rf = run_dir / ("image_%d_response.txt" % idx)
        if not rf.exists():
            entry["status"] = "no_response_file"
            entry["elapsed_s"] = round(time.time() - t0, 1)
            meta_all["images"].append(entry)
            print(">> IMAGE %d: [FAIL] no response captured" % idx)
            continue

        pres = parse_response(rf.read_text(encoding="utf-8"))
        if not pres["ok"]:
            entry["status"] = "rejected"
            entry["reason"] = pres.get("reason")
            entry["error_detail"] = pres.get("detail")
            entry["elapsed_s"] = round(time.time() - t0, 1)
            meta_all["images"].append(entry)
            print(">> IMAGE %d: [REJECTED] 0 credit (reason: %s)" % (idx, pres.get("reason")))
            if pres.get("detail"):
                print("   detail:", pres["detail"][:300])
            continue

        data = pres["data"]
        urls = list(dict.fromkeys(find_urls(data)))
        info = {"signed_url": urls[0] if urls else None}
        try:
            rec = data[0][0]
            info["media_id"] = rec[0]
            info["item_id"] = rec[2] if len(rec) > 2 else None
            gs = rec[6]
            if isinstance(gs, list) and gs and isinstance(gs[0], list):
                info["seed_echo"] = gs[0][1]
                info["prompt_echo"] = gs[0][7]
            if isinstance(gs, list) and len(gs) > 2 and isinstance(gs[2], list):
                info["resolution"] = gs[2]
        except Exception:
            pass
        try:
            pi = data[1][0]
            if isinstance(pi[3], list):
                info["title"] = pi[3][0]
                info["generation_id_echo"] = pi[3][5] if len(pi[3]) > 5 else None
                info["media_id_echo"] = pi[3][4] if len(pi[3]) > 4 else None
            if len(pi) > 4:
                info["project_echo"] = pi[4]
        except Exception:
            pass
        entry.update(info)
        entry["seed_match"] = (info.get("seed_echo") == entry.get("seed"))
        gid = (info.get("generation_id_echo") or "")
        entry["generation_id_match"] = bool(entry.get("generation_id")) and \
            (gid.upper() == str(entry.get("generation_id")).upper())

        if info.get("signed_url"):
            dest = run_dir / ("image_%d_%s.jpg" % (idx, slugify(prompt)))
            okdl = download(info["signed_url"], dest)
            entry["download_ok"] = okdl
            entry["file"] = str(dest) if okdl else None
        else:
            entry["download_ok"] = False
        entry["status"] = "ok" if entry.get("download_ok") else "ok_no_download"
        entry["elapsed_s"] = round(time.time() - t0, 1)
        meta_all["images"].append(entry)
        if entry["status"] == "ok":
            print(">> IMAGE %d: [OK] %s (%s) | seed %s matched=%s | %ss"
                  % (idx, entry.get("file"), entry.get("title"),
                     entry.get("seed"), entry.get("seed_match"), entry.get("elapsed_s")))
        else:
            print(">> IMAGE %d: [WARN] server OK but download failed" % idx)

    # summary
    (run_dir / "metadata.json").write_text(
        json.dumps(meta_all, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + "=" * 64)
    print("SUMMARY:")
    ok_cnt = 0
    for e in meta_all["images"]:
        st = e.get("status")
        if st == "ok":
            ok_cnt += 1
        print("  image %d: %-16s %s" % (e.get("index"), st, e.get("file") or ""))
        if e.get("signed_url"):
            print("      media=%s seed=%s echo=%s %s"
                  % (e.get("media_id"), e.get("seed"), e.get("seed_echo"), e.get("resolution")))
    print("  successful images: %d/%d" % (ok_cnt, len(meta_all["images"])))
    print("  metadata:", run_dir / "metadata.json")
    print("=" * 64)

    # best-effort: disarm the block so the app stays usable afterwards
    try:
        harness_call("print('DISARM:', js('(() => { window.__blockOgi = false; return true; })()'))",
                     timeout=60)
        print("(page block disarmed: window.__blockOgi=false)")
    except Exception:
        pass

    # best-effort: reload the project page so accepted images become visible in the UI
    if not args.dry_run and ok_cnt > 0:
        try:
            prog = (
                "import time\n"
                "cdp('Page.navigate', url=%r)\n"
                "time.sleep(10)\n"
                "print('REFRESHED:', js('document.title'))\n"
            ) % ("https://flow.google.com/project/" + project)
            harness_call(prog, timeout=120)
            print("(project page refreshed — the new image(s) are now visible in the grid)")
        except Exception:
            pass
    return 0 if ok_cnt == len(meta_all["images"]) or args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
