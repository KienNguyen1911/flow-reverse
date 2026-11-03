"""FlowBridge — direct Playwright/CDP bridge to Google Flow inside CloakBrowser.

Production port of the validated Phase-4 experiments (E7/E8/R2). Replaces the
browser-harness dependency with plain Playwright `connect_over_cdp`.

Validated recipe (see `docs/api_specs/flow_create_image.md` §7.5):
  1. Attach over CDP to the running CloakBrowser; find the flow.google.com tab.
  2. Install an idempotent fetch hook: block + capture the app's own ogiZ0b
     request (0 credit spent on the decoy) — the captured body carries the fresh
     reCAPTCHA token minted by the app.
  3. SPA-nav home -> project, type the prompt, click Generate (like a user).
  4. Build OUR OWN ogiZ0b body from the captured token (uppercase UUIDs,
     `_reqid` = app_reqid + 100000, int32 seed) and fire it in-page within ~100 ms.
  5. Long-poll the in-page promise, JSON-decode the two-layer envelope, extract
     the signed CDN URL, download the JPEG/PNG/WEBP with backoff.

Session context for the other RPCs (jHPbke / UpteDb) comes from
`window.WIZ_global_data.SNlM0e` (at) + `FdrFJe` (f.sid) + the latest batchexecute
performance entry (bl / hl / _reqid) — verified live read-only 2026-10-18.

Layout — this module is the public facade; the implementation lives in ``Bridge/flow/``:

  common      constants, ``enc``/``jitter``/``new_seed``, exception hierarchy
  hook_js     ``HOOK_JS`` (in-page fetch block + capture)
  protocol    pure envelope parsing / URL building / reject descriptions + data carriers
  session     CDP attach, lifecycle, in-page eval, hook install, SPA navigation
  composer    prompt typing, image mode/aspect/model/count, guarded Generate click
  references  reference-image attach (synthetic paste / file input)
  transport   session ctx, decoy capture, in-page fire + long-poll, CDN download

Every name that used to live here is re-exported so ``from src.Bridge.flow_bridge import X``
keeps working.
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable, Optional

from playwright.sync_api import CDPSession, Page

# ``importlib.reload(flow_bridge)`` (WebUI hot-reloads the bridge per auto-tryon job) re-executes
# only this file; reload the implementation modules too so edits under ``Bridge/flow/`` apply.
# On first import ``FlowBridge`` is not yet in globals, so this is a no-op.
if "FlowBridge" in globals():
    for _name in ("common", "hook_js", "protocol", "session", "composer", "references", "transport"):
        importlib.reload(sys.modules[f"{__package__}.flow.{_name}"])

from .flow.common import (  # noqa: E402,F401
    DEFAULT_CDP_URL,
    DEFAULT_UA,
    FLOW_ORIGIN,
    SEED_MAX,
    BridgeError,
    CaptureTimeoutError,
    EventFn,
    FireTimeoutError,
    HttpStatusError,
    NoFlowTabError,
    PageInteractionError,
    TokenParseError,
    enc,
    jitter,
    new_seed,
)
from .flow.composer import ComposerMixin  # noqa: E402
from .flow.hook_js import HOOK_JS  # noqa: E402,F401
from .flow.protocol import (  # noqa: E402,F401
    AppCapture,
    FireResult,
    SessionCtx,
    build_capture_fire_url,
    build_rpc_url_from_template,
    describe_reject,
    extract_app_reqid,
    find_signed_urls,
    parse_app_capture,
    parse_batchexecute_text,
    parse_captured_args,
)
from .flow.references import ReferenceMixin  # noqa: E402
from .flow.session import SessionMixin  # noqa: E402
from .flow.transport import TransportMixin  # noqa: E402


class FlowBridge(SessionMixin, ComposerMixin, ReferenceMixin, TransportMixin):
    """Attach to the running CloakBrowser over CDP and drive the Flow tab.

    Usage:
        with FlowBridge(cdp_url) as br:
            br.install_hook()
            br.nav_project(pid)
            ...
    """

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        log: Optional[Callable[[str], None]] = None,
        allow_new_tab: bool = True,
        page_timeout_ms: int = 30000,
    ):
        self.cdp_url = cdp_url
        self._log = log or (lambda *_: None)
        self.allow_new_tab = allow_new_tab
        self.page_timeout_ms = page_timeout_ms
        self._pw = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self._cdp: Optional[CDPSession] = None
