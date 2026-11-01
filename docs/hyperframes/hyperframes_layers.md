# HyperFrames — Sáu lớp, và cách nhúng vào Flow Bench

> Kết quả nghiên cứu lớp (deep pass) trên `hyperframes@0.8.221`, kèm **kiểm chứng chạy thật**
> trên Windows (Node 24.16.0). Mọi khẳng định đánh dấu ✅ đã verify; 🔶 là suy luận, chưa chạy thử.
>
> Ngày: 2026-10-30.

---

## 0. TL;DR

HyperFrames **không phải hai sản phẩm** (app vs CLI). Nó là **một project folder** gồm HTML +
CSS + media, được đọc/ghi bởi sáu lớp bề mặt. Khác biệt app/CLI thuần tuý là **bề mặt điều
khiển**, không phải định dạng hay engine.

```text
project folder (index.html + assets/)
   ├── Studio app        (desktop: chat + agent + review)
   ├── Browser editor    (npx hyperframes preview — chính là Studio SPA)
   ├── CLI               (init/check/render/timeline/...)
   ├── SDK               (@hyperframes/sdk — sửa bằng code, không cần browser)
   ├── Player            (@hyperframes/player — nhúng phát trong web)
   └── Producer          (@hyperframes/producer — render trong Node)
```

Với Flow Bench:

| Nhu cầu | Dùng |
| :--- | :--- |
| Render hàng loạt, tất định, trong job runner | **CLI** (`render --batch --json`) |
| QA trước khi render | **CLI** (`lint`, `check --json`) |
| Sửa tay / duyệt template bởi người | **`hyperframes preview`** nhúng iframe |
| Sinh biến thể mỗi run | **variables + `--batch`**, không sinh HTML mới |
| App MCP (`127.0.0.1:59545`) | **Không** đưa vào production loop |

---

## 1. Sáu lớp

| Lớp | Package / bề mặt | Vai trò | Ghi chú |
| :--- | :--- | :--- | :--- |
| **Contract** | HTML `data-*` | Nguồn chân lý duy nhất | Mọi lớp đọc/ghi cùng file |
| **Core** | `@hyperframes/core` | Types, compiler, variables, runtime | Subpath `/compiler`, `/variables`, `/composition-contract`, `/runtime` |
| **SDK** | `@hyperframes/sdk` | Sửa composition bằng code, headless | `openComposition` → query → mutate → `serialize()` |
| **Studio lib** | `@hyperframes/studio` + `@hyperframes/studio-server` | React components + Hono API backend | Building blocks, **không** drop-in |
| **Player** | `@hyperframes/player` | `<hyperframes-player>` nhúng | Chỉ play/seek |
| **Producer** | `@hyperframes/producer` | `createRenderJob` + `executeRenderJob` | Render trong Node |
| **CLI** | `hyperframes` | Bề mặt đầy đủ nhất | Bao trùm cả 5 lớp trên |

---

## 2. Contract HTML

Đọc `reference/html-schema`, `concepts/compositions`, `concepts/data-attributes`, đối chiếu
project thật (`Untitled 2`):

- **Timing nằm trong HTML**, không trong JS. `data-start` / `data-duration` / `data-end` là
  nguồn chân lý; runtime bật/tắt visibility theo đó.
- **`data-track-index` chỉ là lane của timeline editor.** Render **bỏ qua** → đừng dùng để suy
  ra z-order.
- **Animation** đăng ký qua `window.__timelines[<composition-id>] = gsap.timeline({paused:true})`.
  Render seek từng frame: `tl.seek(t)`.
- **Nested composition**: host có `data-composition-id` + `data-composition-src="compositions/x.html"`,
  file con bọc trong `<template>`.
- **`data-media-start`**: offset trong file nguồn (dùng khi trim clip).
- **Determinism**: fps/width/height/variables **bị khoá trước frame 0**. Cấm `Date.now()`,
  random không seed, fetch giữa render. ✅ `--variables` cho ra pixel khác nhau một cách tất định
  (frame hash khác nhau giữa bản xanh và đỏ).

---

## 3. Ba bề mặt cho người

### 3.1 Studio app (desktop)

Không phải "renderer có UI" — là **chat + agent + review**.

- Chat với agent (Claude Code / Codex / …), `@` chèn moment/media/file/project, `#` gọi tool như
  **Storyboard**.
- Trỏ / khoanh / vẽ / comment lên khung hình → gửi agent.
- Canvas, Layers, Design panel, Timeline, Assets, Catalog, Renders panel (export GIF/MP4).
- **MCP server per-session** tại `127.0.0.1:59545/mcp`, bearer token ở
  `%APPDATA%\HyperFrames\mcp.json`.

✅ `tools/list` đã verify — toàn bộ bề mặt app:

```text
project.list/get/create/open/close      media.*        comments.*
agent.run / agent.jobs / agent.wait / agent.steer / agent.cancel
preview.frame     ui.navigate
file.read / file.write
render.start / render.wait
skill.read        read_style
history.begin / end / list / undo
image.proposeSelection    media.cutOut    image.erase
```

✅ `preview.frame` trả **PNG base64 thật** (đã lấy frame tại `t=3`). Đây là đường duy nhất lấy
1 frame **không cần render**.

⚠️ **Mỗi session app là một server riêng, token riêng, chỉ sống khi app mở.** Không có cách nào
đảm bảo nó tồn tại trong batch job lúc 3h sáng → **không đưa vào production loop**.

### 3.2 Browser editor — `npx hyperframes preview`

✅ **Đây chính là Studio SPA đầy đủ**, không phải bản rút gọn. Verify: `<title>HyperFrames Studio</title>`,
`window.__HF_CLI_DISTINCT_ID`, `/__hyperframes_config` trả `{"isHyperframes":true,...}`.

Đây là bề mặt **giàu nhất để sửa tay**:

| | Studio app | Browser editor |
| :--- | :--- | :--- |
| Sửa tay trên canvas | qua agent là chính | **đầy đủ inspector** |
| Design panel | hạn chế | crop, rotation, guides, nudge, exact values |
| Keyframes | qua agent | **trực tiếp trên timeline** |
| Variables UI | có | **tạo/bind/preview override, copy ra lệnh render** |
| Hot reload | – | ✅ |
| WebMCP (`studio_look`, `studio_select`, `studio_inspect`) | – | ✅ |
| Agent chat | ✅ | – |

Flags: `--background`, `--foreground`, `--status --json`, `--list`, `--port` (default 3002),
`--proxy` (auto transcode HEVC/ProRes/AV1 sang proxy cache), `--browser-gpu`/`--no-browser-gpu`.

### 3.3 CLI

Bề mặt **duy nhất** bao trùm tất cả:

| Nhóm | Lệnh |
| :--- | :--- |
| Tạo & nạp liệu | `init`, `add`, `catalog`, `capture`, `transcribe`, `models`, `tts`, `remove-background`, `media-treatment`, `media-use`, `beats`, `audio` |
| Xem | `normalize-audio`, `preview`, `present`/`play`, `publish`, `open`/`catch-up` |
| Kiểm | `lint`, `check`, `snapshot`, `keyframes`, `compare`, `grade-compare` |
| Phân tích ngược | `measure`, `diff` |
| Sửa | `timeline` (move/trim/split/set/duplicate/delete/ids), `history` (begin/end/list/undo) |
| Render | `render`, `benchmark` |
| Vận hành | `doctor`, `clean`, `info`, `compositions`, `upgrade`, `browser`, `docs`, `feedback`, `telemetry`, `skills`, `usage`, `billing`, `figma`, `events` |
| Cloud | `auth login/status/refresh/logout`, `cloud render/list/get/delete` |

**Chỉ CLI có** (app MCP không có): `check`, `snapshot`, `keyframes`, `compare`, `grade-compare`,
`benchmark`, `measure`, `diff`, `beats`, `audio --read`, `normalize-audio`, `capture`, `transcribe`,
`tts`, `remove-background`, `--docker`, HDR/4K, `--resume` segmented capture.

---

## 4. SDK — lớp cho "edit trong app"

### 4.1 Vòng lặp cốt lõi

```ts
const comp = await openComposition(html);   // stamp data-hf-id lên mọi element
comp.setText(id, "Shipped.");
comp.setStyle(id, { color: "#FFD60A", fontSize: "96px" });
comp.setTiming(id, { start: 0.5, duration: 4 });
const out = comp.serialize();
```

`openComposition` là entry point duy nhất. Ba mode:

| Mode | Khi nào | History | Persist |
| :--- | :--- | :--- | :--- |
| **Standalone** (default) | bạn sở hữu HTML | SDK tự quản | bạn tự `serialize()` |
| **Persist** (`persist` + `persistPath`) | ghi thẳng ra đĩa | SDK quản | `createFsAdapter({root, maxVersions})` |
| **Overrides** (`overrides`) | layer mỏng trên template gốc | host quản | tách base/override |

Mode **overrides** chính là thứ đáng giá cho lookbook: một template gốc dùng chung, mỗi run chỉ
ghi phần sai khác.

### 4.2 Bề mặt

- **Query**: `getElements()`, `find({tag|text|name|track|composition})`, `getElement`, `getRootElements`,
  `getAllAnimationIds`, `listVariables`, `getElementTimings`, `can(op)`
- **Mutation** (đều đi qua `dispatch()`): `setText`, `setStyle`, `setAttribute`, `setTiming`,
  `setMediaStart`, `setVolume`, `setPlaybackRate`, `setTrack`, `addGsapTween`, `setGsapTween`,
  `addLabel`, `replaceWithKeyframes`, `declareVariable`, `duplicate`, `delete`, `replace`, `move`
- **History**: `undo`, `redo`, `canUndo`, `canRedo`; mọi thay đổi emit **RFC 6902 JSON Patch**;
  `batch()` gộp nhiều op thành một bước undo/persist
- **Adapters**: `PersistAdapter` (`createFsAdapter` → `.hf-versions/<ts>-<seq>.html`),
  `PreviewAdapter` (`createIframePreviewAdapter`, iframe **same-origin**)
- **`@hyperframes/sdk/editing`**: `resolveElementAffordances(liveEl, modelEl)` → `{capabilities, sections}`

### 4.3 Quirk đã kiểm chứng

| Quirk | Hệ quả |
| :--- | :--- |
| `ElementSnapshot.duration` = **null** với `<img data-duration>` và element chỉ có `data-end` | **Đừng** đọc `duration`. Dùng `getElementTimings()[id].exitAt` |
| `find({composition})` trả `[]` cho host `data-composition-src` | Scene ngoài **không** được inline. Phải `openComposition()` riêng file sub-composition |
| `getElement("hf-xxx")` → `null` nếu element ở file sub-composition ngoài | Như trên |
| `serialize()` **giữ nguyên** `<template>` + `data-composition-src` | An toàn để ghi đè file thật |
| `declareVariable` serialize HTML-escaped (`&quot;`) | Xấu nhưng `lint` pass 0/0 |
| `addGsapTween`/`setGsapTween` ghi selector `[data-hf-id="hf-xxx"]` | Không phụ thuộc `id`/class |
| Tween id sinh theo **vị trí**, đánh số lại sau `replaceWithKeyframes` | Đừng cache animation id lâu dài |
| `scrollTrigger` bị strip | Không dùng cho render |

---

## 5. Ma trận năng lực

| Việc | App | Editor | CLI | SDK |
| :--- | :-: | :-: | :-: | :-: |
| Chat/sửa bằng ngôn ngữ tự nhiên | ✅ | – | – | – |
| Khoanh/vẽ/comment lên frame | ✅ | – | – | – |
| Sửa tay property, kéo/resize/crop | hạn chế | ✅ | – | – |
| Keyframes trên timeline | – | ✅ | – | ✅ |
| Play/seek | ✅ | ✅ | `play` | – |
| Sửa timing hàng loạt | qua agent | – | ✅ | ✅ |
| Undo/redo có nhãn | ✅ | ✅ | `history` | ✅ |
| Lint / check / snapshot | – | – | ✅ | – |
| Beats, stems, TTS, transcribe | – | – | ✅ | – |
| Remove background | `media.cutOut` | – | ✅ | – |
| Render MP4/WebM/GIF/PNG/HLS | ✅ | ✅ | ✅ | – |
| Batch theo variables | – | – | ✅ | – |
| Render trong process Node | – | – | – | Producer |
| Nhúng player vào web | – | – | – | Player |
| Headless CI/server | – | – | ✅ | ✅ |
| Lấy 1 frame không render | ✅ | – | `snapshot` | – |
| Publish / share link | ✅ | ✅ | `publish` | – |
| Cloud render | – | – | ✅ | – |

---

## 6. Số đo thật (project 1080×1920, 60fps, 16s)

| Lệnh | Thời gian | Kết quả |
| :--- | ---: | :--- |
| `info --json` | <1s | 6 elements, 4 tracks, 65 MB |
| `lint --json` | <1s | **0 error, 1 warning** (`subcomposition_style_outside_template`) |
| `check --json --no-contrast` | **13.3s** | ok=true, runtime 0, layout 1 info, craft 3 |
| `check --json` (full) | ~15s | + contrast **1 warning** |
| `render` 24fps draft low-memory | **50.6s** | 8.2 MB, exit 0 |
| `render --batch` 2 rows @12fps | 10.9s + 9.0s | `{"type":"batch-complete",...}` |

`check` bắt đúng 3 lỗi craft thật:
- `line_unread`: `"9.0"` và `"/ 10"` hiện 1.89s < ngưỡng 2.00s
- `text_below_floor`: 3 element < 28px, nhỏ nhất `"FINAL FIT CHECK"` = 15px

→ Đây là **QA tự động miễn phí** mà app không có.

---

## 7. Biên giới CLI — cái bẫy đã đâm phải

| Bẫy | Thực tế |
| :--- | :--- |
| `render --json` "im lặng" khi thành công | **In rỗng**. Muốn JSON phải `--batch` → `{"type":"batch-complete","manifestPath","rows":[{outputPath,status,durationMs,renderTimeMs}]}` |
| `timeline move '#x'` với positional dir | **Sai**. Edit command dùng `--dir ./proj`. `timeline ids` lại **từ chối** positional dir |
| PowerShell nuốt `#` thành comment | Lỗi giả `{"code":"refused","message":"'#x' was not found"}`. Phải chạy qua `cmd /c '... "#x" ...'` |
| Timeline edit "phá" file | **Reformat toàn bộ** (self-closing → non-self-closing, stamp `data-hf-id`), có `backupPath` trong `.hyperframes/backup/` |
| `timeline split` | Ghi `data-media-start` cho **cả hai** nửa |
| `timeline set` | Chỉ nhận `volume`, `rate`, `track` |
| `--strict-variables` | **Fail cả batch** nếu bất kỳ row có key không khai báo |
| `--batch` output trùng | **Fail** nếu `-o ./x.mp4` mà 2 rows → phải có placeholder `-o ./v_{hookTitle}.mp4` |
| `--duration` trên `render` | **Không tồn tại** (exit 2, `unknown_flag`) |
| `--variables` có đổi pixel? | **Có** (frame MD5 khác nhau) |
| `preview --stop` từ ngoài project | **Fail** (`preview-stop-failed: No composition found`). Phải `cd` vào chính project dir rồi mới `--stop` |

Khác:
- Studio tạo project pin `hyperframes@0.8.210`; docs ghi `0.8.216`; npm latest **0.8.221**.
- ✅ `open --json` **chạy trên Windows** (dù docs nói hand-off chỉ macOS).
- ✅ `catch-up` trả rỗng trừ khi hand-off bắt đầu **trong** agent session.
- ✅ App MCP `project.list` cần `arguments: {}`, không phải `[]`.

---

## 8. `HF_TOOL_CONTEXT` — dùng cho job runner

```bash
HF_TOOL_CONTEXT='{"version":1,"capabilities":{
  "events": {"transport": {"type":"ndjson-file","path":"/tmp/call-42/events.ndjson"}},
  "project-lock": {"waitMs": 90000}
}}'
```

- `events` → CLI ghi NDJSON những gì nó tạo (ảnh, snapshot…), harness đọc rồi xoá. Giải đúng vấn
  đề "`render --json` in rỗng".
- `project-lock` → CLI **chờ** thay vì race khi nhiều job cùng chạm một project.

Không set thì hành vi y như terminal → rủi ro bằng 0 khi thêm vào.

---

## 9. `npx hyperframes preview` phơi ra API gì (verify thật)

Server là **Hono**, mount Studio API tại `/api`. ✅ Route thật (trích từ
`hyperframes/dist/chunk-ZKPRJPWN.js` và đã gọi thử):

```text
GET    /api/projects                          -> {"projects":[{id,dir,title}]}
GET    /api/projects/:id                      -> manifest + toàn bộ file list
GET    /api/projects/:id/preview              -> HTML đã bundle (kèm scene parts, gsap fallback)
GET    /api/projects/:id/preview/*
GET    /api/projects/:id/lint                 -> findings[]
GET    /api/projects/:id/signature            -> hash để biết file đã đổi
GET    /api/projects/:id/renders              -> {"renders":[]}
GET    /api/projects/:id/selection
PUT    /api/projects/:id/selection
GET    /api/projects/:id/files/*              -> nội dung file
PUT    /api/projects/:id/files/*              -> ghi file
PATCH  /api/projects/:id/files/*              -> patch file
DELETE /api/projects/:id/files/*
POST   /api/projects/:id/upload
POST   /api/projects/:id/duplicate-file

POST   /api/projects/:id/file-mutations/patch-element/*
POST   /api/projects/:id/file-mutations/patch-element-batches
POST   /api/projects/:id/file-mutations/patch-elements-batch/*
POST   /api/projects/:id/file-mutations/probe-element/*
POST   /api/projects/:id/file-mutations/probe-elements/*
POST   /api/projects/:id/file-mutations/remove-element/*
POST   /api/projects/:id/file-mutations/remove-elements/*
POST   /api/projects/:id/file-mutations/split-element/*
POST   /api/projects/:id/file-mutations/split-batch
POST   /api/projects/:id/file-mutations/wrap-elements/*
POST   /api/projects/:id/file-mutations/unwrap-elements/*
POST   /api/projects/:id/file-mutations/insert-composition/*
POST   /api/projects/:id/file-mutations/freeze-frame

POST   /api/projects/:id/gsap-mutations/*
POST   /api/projects/:id/gsap-mutations-batch/*
POST   /api/projects/:id/gsap-mutation-rollback/*
GET    /api/projects/:id/gsap-mutation-capabilities
GET    /api/projects/:id/gsap-animations/*

POST   /api/projects/:id/render               -> job id
GET    /api/render/:jobId/progress            -> SSE
GET    /api/render/:jobId/download
GET    /api/render/:jobId/view
POST   /api/render/:jobId/cancel
DELETE /api/render/:jobId

GET    /api/projects/:id/thumbnail/*
GET    /api/projects/:id/image-thumbnail/*
GET    /api/projects/:id/waveform/*
GET    /api/projects/:id/peaks/*
GET    /api/projects/:id/media/metadata
POST   /api/projects/:id/media/remove-background
POST   /api/projects/:id/loudness/normalize
GET    /api/projects/:id/preview/comp/*
GET    /api/registry/blocks
GET    /api/assets/global
GET    /api/fonts, /api/fonts/google, /api/fonts/file
GET    /api/media-jobs/:jobId/progress
GET    /api/environment/ffmpeg
GET    /api/events
GET    /api/vendor/npm/gsap@*/dist/*
```

Nghĩa là: **toàn bộ năng lực edit của Studio đều là HTTP**. Không cần reverse-engineer gì thêm.

### 9.1 Ba ràng buộc cứng đã verify

| Ràng buộc | Bằng chứng | Hệ quả |
| :--- | :--- | :--- |
| **Không có CORS** | `/api/projects` với `Origin: http://127.0.0.1:8080` → 200 nhưng **không** header `Access-Control-Allow-Origin`; `OPTIONS` → **404** | Browser ở port khác **không** `fetch()` được. Phải proxy hoặc iframe |
| **Ghi cần write-token** | `POST /file-mutations/probe-element` không token → **400**; client gửi header `X-Hyperframes-Write-Token` | Không tự sinh request từ Flow Bench nếu chưa lấy token |
| **Không chặn iframe** | `/` không có `X-Frame-Options`, không có `frame-ancestors` | ✅ **Nhúng iframe từ port khác được** |

Ngoài ra `/__hyperframes_config` trả `{"isHyperframes":true,"pid","projectName","projectDir","version"}`
— dùng làm health check.

---

## 10. Trả lời: "tách service nhiều port có ổn không?"

**Ổn, nhưng phải đúng kiểu.** Ranh giới không phải "mỗi thứ một port", mà là:

```text
┌─────────────────────────────────────────────────────────────┐
│ Browser                                                     │
│                                                             │
│  :4001 Flow Bench (React 19 + Vite)                         │
│    └── <iframe src="http://127.0.0.1:4610/#project/...">    │ ← ✅ được
│         (Studio editor, full)                               │
│                                                             │
│  :4001 → /api/*  (Vite proxy) → :4000 FastAPI               │
└─────────────────────────────────────────────────────────────┘

  :4000 FastAPI (Flow Bench backend, job runner)
    └── spawn: npx hyperframes render/check/lint   ← production loop
    └── proxy: /studio-api/* → :4610/api/*          ← nếu cần đọc từ FE

  :4610 hyperframes preview (Studio editor + Studio API)
    └── 1 instance / 1 project, headless-able
```

### Vì sao iframe đúng còn fetch sai

- `iframe` = **document navigation**, CORS không áp dụng → ✅ chạy ngay.
- `fetch()` từ `:4001` sang `:4610` = cross-origin, server **không** trả CORS header và preflight
  404 → ❌ chặn cứng.

→ Nếu Flow Bench cần **đọc** dữ liệu Studio (vd. danh sách element, lint), hãy để **FastAPI
proxy** (`:4000 → :4610`). Server-to-server không bị CORS.

### Vì sao phải 1 preview server / 1 project

`preview` bind project vào server lúc khởi động (`--port`, một `--background` instance giữ đúng
một `projectDir`). Với N lookbook:

| Cách | Đánh giá |
| :--- | :--- |
| N port, N preview server | ❌ tốn ~N × Chromium, pid/token/log mỗi cái; `--list` phải dọn |
| **1 port, start theo project đang mở, `--stop` khi chuyển** | ✅ đơn giản, chấp nhận ~1–2s chuyển |

### Vị trí của từng port

| Port | Service | Vai trò | Có trong production loop? |
| :--- | :--- | :--- | :--- |
| `:4000` | FastAPI (`src/WebUI/app.py`) | Job runner, API, serve file | ✅ |
| `:4001` | Vite (dev) | Flow Bench FE | dev only |
| `:4610` (đề xuất) | `hyperframes preview --background` | **Studio editor cho người** | ❌ chỉ human-in-loop |

---

## 11. Kiến trúc đề xuất cho Flow Bench

### 11.1 Production loop (không có browser, không có app)

```text
lookbooks/<slug>/
├── index.html                 # template + data-composition-variables
├── assets/{clip1.mp4,clip2.mp4,items/*.png,audio/*}
└── renders/

Flow Bench job kind "lookbook_render":
  1. lint  --json         -> fail nếu errorCount > 0
  2. check --json         -> fail nếu errorCount > 0; craft/contrast chỉ report
  3. render --batch rows.json -o renders/{slug}.mp4 --json
                          -> đọc {"type":"batch-complete", rows[]}
  4. bind output qua workspace asset, serve qua /api/node/files/...
```

Bắt buộc:
- Parse kết quả từ `--batch`, **không** parse stdout.
- Đặt `HF_TOOL_CONTEXT` để lấy `events` + `project-lock`.
- **Không** dùng ffmpeg concat của repo cho lookbook — `flow_video_bridge.py` (~753, ~803) và
  `watermark_remover.py` (~464) encode `-an` → **mất audio**. HyperFrames render đã mix audio.

### 11.2 "Edit" cho người (phương án C thu gọn)

Không cần viết lại editor. Chỉ cần:

1. `POST /api/lookbook/{slug}/studio/start` → FastAPI spawn
   `npx hyperframes preview ./lookbooks/<slug> --background --port 4610 --no-open --json`,
   đọc `serverUrl` + `pid` từ JSON.
2. Trả `studioUrl` (`http://127.0.0.1:4610/#project/<slug>`) cho FE.
3. FE render `<iframe src={studioUrl}>`.
4. `POST /api/lookbook/{slug}/studio/stop` → **phải `cwd=lookbooks/<slug>`** rồi mới
   `preview --stop` (✅ verified: gọi từ ngoài project dir trả `preview-stop-failed`;
   gọi trong đúng dir trả `{"state":"stopped"}` và port xuống ngay).
5. Nếu FE cần đọc dữ liệu Studio → proxy `/studio-api/*` qua FastAPI.

Ưu điểm: **không** phải `npm install @hyperframes/studio`, **không** phải tự dựng Hono adapter,
**không** phải viết lại canvas/timeline/inspector. Vẫn là editor thật, đầy đủ.

### 11.3 Khi nào mới cần SDK sidecar

Chỉ khi cần **sửa bằng code mà không mở UI** — ví dụ sinh 50 biến thể biến đổi sâu hơn
variables cho phép (đổi cấu trúc, thêm/xoá element), hoặc áp patch từ agent.

Lúc đó: một process Node nhỏ giữ `openComposition` + `createFsAdapter`, expose HTTP nội bộ.
Cho patch event, undo/redo, `resolveElementAffordances` — **không cần browser**.

Với lookbook hiện tại, **variables + `--batch` là đủ** → chưa cần bước này.

---

## 12. Rủi ro đã biết

| Rủi ro | Mức | Giảm thiểu |
| :--- | :--- | :--- |
| `preview` version drift (project pin 0.8.210, CLI 0.8.221) | Trung bình | Pin `hyperframes` trong `package.json` của từng lookbook; kiểm `__hyperframes_config.version` |
| Chromium do preview chiếm RAM | Trung bình | Chỉ start khi người mở; `--stop` khi đóng; timeout idle |
| Port 4610 bận | Thấp | Đọc `port` từ JSON trả về, không hardcode |
| Studio API đổi giữa minor | Trung bình | Chỉ dùng route ổn định (`/projects`, `/preview`, `/lint`, `/files/*`, `/render`); tránh `file-mutations/*` nếu không cần |
| `-an` trong ffmpeg của repo | **Cao** | Không dùng concat path cho lookbook; dùng render của HyperFrames |
| Write-token | Thấp | FE không ghi trực tiếp; mọi ghi đi qua Studio UI hoặc FastAPI |

---

## 13. Việc chưa làm

- Chưa verify `POST /api/projects/:id/render` end-to-end (chỉ verify route tồn tại + SSE progress).
- Chưa verify write-token lấy từ đâu chính xác (client gửi `X-Hyperframes-Write-Token`, nguồn
  là `N4t()` trong bundle — cần đọc thêm nếu muốn ghi bằng tay).
- Chưa test iframe nhúng thật từ `:4001` (mới verify header không chặn).
- Chưa test 2 preview server cùng lúc.
