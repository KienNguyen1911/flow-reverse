# Báo cáo thay đổi — Prompt video Lookbook có timeline & QA clip thô

**Ngày:** 2026-11-02
**Phạm vi:** `src/Workflows/`, `web/src/`, `configs/lookbook_script.json`, `prompt-skills/`
**Commit:** `64efb49` → `d1b52db` → `dcd29ad`
**Tổng:** 25 file, +2900 / −43 dòng

---

## 1. Vấn đề ban đầu

Prompt video Lookbook quá ngắn và không có cấu trúc thời gian. Hệ quả quan sát được:

- Prompt chỉ là một câu mô tả chung, không nói 2 giây đầu phải làm gì ⇒ Flow trả clip mà hook
  không đứng yên, người xem lướt qua trước khi kịp đọc chữ.
- Không có "điều cấm" ⇒ Flow tự thêm chuyển động ngoài ý muốn.
- Hai node video trong cùng canvas gửi **prompt giống hệt nhau**, vì không node nào biết nó là
  clip nào. Không có khái niệm hook vs showcase trong dữ liệu.
- Không ai kiểm **thứ Flow trả về**. Pipeline chỉ lint prompt (kiểm điều mình xin), nên clip
  720×1280 lẫn board UI burn-in vẫn đi thẳng vào HyperFrames.

Ràng buộc kỹ thuật quyết định cách sửa: `build_video_args`
(`src/Bridge/flow_video_bridge.py:263`) chứng minh payload Flow chỉ có **một chuỗi prompt** —
không có trường negative, không có trường timeline. Vì vậy mọi cấu trúc thời gian phải sống
trong câu văn, và phải sống sót qua `sanitize_video_prompt`.

---

## 2. Kiến trúc sau khi sửa

```
configs/lookbook_script.json     ← nguồn sự thật: goal, beats[], negative[] cho từng clip
            │
            ├── motion_prompt.beats_to_prompt()   ← renderer TẤT ĐỊNH: beats → văn xuôi
            │            │
            │            └── sanitize_video_prompt(p, aggressive=False) == p.strip()   ← gate
            │
            ├── prompt_agent._beat_lines()        ← agent đọc beats + prompt đã render
            │
            └── raw_video_qa.evaluate_clip()      ← đo clip Flow trả về, 9 gate
                         │
                         └── delivery.json → clips[].qa + qa_summary → README
```

Nguyên tắc chi phối: **renderer sở hữu câu chữ, agent chỉ được thêm `custom_hint`.**
Nếu agent được viết lại, mỗi lần chạy ra một prompt khác và gate round-trip vô nghĩa.

---

## 3. Thay đổi theo từng commit

### 3.1. `64efb49` — Beats trong script + renderer prompt tất định

**`configs/lookbook_script.schema.json`** (+38): `clips[]` nhận thêm `goal` (chuỗi), `beats[]`
(`at_s`, `duration_s`, `action`, `holds_gaze`, `must_not`), `negative[]`. Tất cả tuỳ chọn để
script cũ không vỡ.

**`src/Workflows/script_contract.py`** (+98/−1): `BeatSpec` dataclass; `ClipSpec.goal/beats/negative`
+ property `has_beats`; `_validate_beats()` kiểm 6 ràng buộc — beat đầu `at_s == 0` (nếu không,
khoảng 0→at_s không ai điều khiển), không hở, không chồng lấn, tổng bằng `duration_s`,
`holds_gaze=True` bắt buộc có `must_not` (giữ mắt mà không nói cấm gì thì model tự bịa),
`action` không rỗng.

**`src/Workflows/motion_prompt.py`** (mới, 272 dòng): renderer tất định.
- `beats_to_prompt(clip)` sinh câu camera + 3 beat theo **văn xuôi thứ tự**.
- `MOTION_VERBS` whitelist, `FORBIDDEN_TERMS` chặn từ vựng UI.
- `MAX_PROMPT_WORDS = 120`.
- Định dạng câu được chọn sau khi thử: chỉ **văn xuôi có thứ tự** sống sót sanitizer. Nhãn
  `0s-2s:` / `0-2s:` / `[0-2s]` bị xoá sạch; `(0s-2s)` để lại rác. Dạng sống byte-for-byte là
  `For the first N seconds … From the Ath to the Bth second … In the final N seconds`.

**`configs/lookbook_script.json`** (+57/−2): clip1 và clip2 mỗi clip có `goal`, 3 beat,
`negative`. `motion_prompt` viết lại thành **bản sao output renderer** để hai nguồn không lệch.

**`prompt-skills/lookbook-video-prompter.md`** (+83/−27): §4–§7 viết lại — mô tả cấu trúc 3 beat,
bỏ template tote/halter cứng, ngân sách 70–100 từ.

**`src/Workflows/prompt_lint.py`** (+60/−4): `VIDEO_MAX_WORDS` 80→**120**, `VIDEO_MIN_WORDS`
10→**40**; `_in_negative_clause()` + `_find_affirmed_in_clause()` để cụm như "without the banner"
không bị tính là từ vựng UI.

**Test mới:** `tests/test_script_beats.py` (14), `tests/test_motion_prompt.py` (21); sửa
`tests/test_prompt_skills_contract.py` (38 passed).

Kết quả renderer: clip1 **110 từ**, clip2 **99 từ**, cả hai round-trip sạch.

### 3.2. `d1b52db` — Node video gửi `clip_id` xuống prompt agent

Lỗi gốc: `CanvasPanel.tsx` / `CanvasDrawer.tsx` gọi `/api/agent/generate-node-prompt` mà không
gửi `clip_id`. Backend đã nhận field này từ lâu, nhưng FE **không có nguồn nào** để biết có clip
nào — nên cả hai node video rơi vào nhánh context rỗng.

| File | Thay đổi |
|:--|:--|
| `src/Workflows/media_service.py` (+32) | `node_options()` trả thêm khối `script` (`path`, `slug`, `duration_s`, `clips[]`) |
| `src/Workflows/prompt_agent.py` (+60) | `_beat_lines()` chèn nhịp có cấu trúc + prompt renderer nguyên văn + "KHÔNG đổi thứ tự"; thiếu `clip_id` in `THIẾU \`clip_id\`` kèm danh sách clip |
| `web/src/types.ts` (+29) | `ScriptClipOption`, `NodeMediaOptions.script`, `CanvasNodeState.clipId` |
| `web/src/hooks.ts` (+38) | `useScriptClips()` — cache chung với `useLimits`, trả `[]` khi backend không có script |
| `web/src/components/CanvasPanel.tsx` (+25/−1) | `SCRIPT_PATH`, `clipRoleOf()`, 2 call site gửi `clip_id`/`clip_role`/`script_path`; template `lb_video_1=clip1`, `lb_video_2=clip2` |
| `web/src/components/CanvasDrawer.tsx` (+50/−2) | select clip cho node video + call site thứ 3 + cảnh báo khi chưa chọn |

**Test mới:** `tests/test_node_options_script.py` (5), `tests/test_prompt_agent_context.py` (13).

Kiểm chứng end-to-end qua HTTP thật: `GET /api/node/options` → `script.clips[0] = {id: clip1,
role: hook, duration_s: 8.0, has_beats: true, goal: …}`. Probe `format_agent_instruction`:
`clip_id=clip1` → `Clip đang viết: clip1 — vai **hook**` + beat `0.0–2.0s`;
`clip_id=None` → dòng `THIẾU \`clip_id\`` + danh sách clip.

### 3.3. `dcd29ad` — QA clip thô trước khi đưa sang HyperFrames

**`src/Workflows/raw_video_qa.py`** (mới, 657 dòng). 9 gate:

| Gate | Đo bằng | Bắt lỗi gì |
|:--|:--|:--|
| `duration_match` | ffprobe | clip dài/ngắn hơn script ⇒ trượt timeline |
| `fps_ok` | ffprobe | file đã qua xử lý khác |
| `resolution_ok` | ffprobe vs canvas | 720×1280 trong composition 1080×1920 |
| `no_hard_cut` | `scdet` | Flow cắt cảnh giữa clip |
| `not_frozen` | `freezedetect` | model trả khung đứng |
| `no_baked_ui` | quét khung 0.1s + `detect_baked_ui_panel` | board UI burn-in |
| `hook_clean` | như trên, so cửa sổ hook | chữ đè đúng phần hook |
| `hook_still` | `tblend`+`signalstats`, trung vị | hook chuyển động, không đọc kịp |
| `chain_match` | SSIM khung nối | `chain_from` lệch ⇒ nhảy hình |

Mỗi gate trả `pass` / `warn` / `skip`. **Không có `fail`** — bạn chọn "chỉ cảnh báo", nên QA
không bao giờ chặn export. Gate không đo được trả `skip` **kèm lý do**, không bịa số.

**Ngưỡng đều lấy từ đo, không phải số tròn.** Đây là phần tốn thời gian nhất:

| Ngưỡng | Giá trị | Căn cứ |
|:--|--:|:--|
| `HARD_CUT_THRESHOLD` | 12 | clip thật đỉnh **10.79** (t=4.0s) vs cắt cứng tổng hợp **15.63** |
| `FREEZE_NOISE_DB` | −50 dB | `-40dB` báo nhầm đoạn 0.5–0.875s (chỉ là chuyển động chậm) |
| `HOOK_STILL_RATIO_MAX` | 0.6 | đo được **0.429** (hook median 0.95 vs thân 4.55) |
| `CHAIN_SSIM_MIN` | 0.90 | SSIM nội bộ clip1 = 0.475 ⇒ gate chỉ có nghĩa cho cặp hai clip |

Việc xác nhận ngưỡng `scdet` cần mở ảnh: đỉnh 10.79 tại t=4.0s nghe như cắt cảnh, nhưng mở
khung t3.9 và t4.0 thấy rõ là **cùng một cảnh, chỉ đổi tư thế** (túi xách xuất hiện).

**`src/Workflows/delivery.py`** (+77): `_attach_clip_qa()` chạy **sau** vòng copy clip — vì
`chain_match` cần khung cuối của clip nguồn, mà clip nguồn chỉ có file ở `dest_clips_dir` sau khi
chính nó được copy. Gắn `clips[].qa`, thêm `manifest["qa_summary"]`
(`status`/`counts`/`ok`/`warnings`/`skipped`), và in bảng QA trong `_render_readme`.

**Test mới:** `tests/test_raw_video_qa.py` (407 dòng, 26 test) — hợp đồng không chặn, `skip` kèm
lý do, gate đo trên clip thật, fixture cắt cứng/đoạn đứng, `hook_window` lấy từ beats, tích hợp
`delivery.json` + README.

---

## 4. Kiểm chứng

```
python -m pytest tests -q
→ 392 passed, 5 failed in 71.64s
```

**5 failure là baseline có sẵn (D-001), không liên quan thay đổi này:** `test_account_pool` ×3 và
`test_media_service` ×2, cùng nguyên nhân — `configs/accounts_pool.json` có thêm entry `9:16: 2`
mà test kỳ vọng chỉ `{"16:9": 3}`. Gate đặt ra từ đầu phiên: **số đỏ không được tăng**. Giữ nguyên.

Riêng các suite của thay đổi này:

```
tests/test_script_beats.py            14 passed
tests/test_motion_prompt.py           21 passed
tests/test_prompt_skills_contract.py  38 passed
tests/test_node_options_script.py      5 passed
tests/test_prompt_agent_context.py    13 passed
tests/test_raw_video_qa.py            26 passed
tests/test_delivery.py                34 passed
```

Frontend:
```
npm run build        → xanh
npx tsc --noEmit     → chỉ còn lỗi có sẵn ở TryOnPanel.tsx, 0 lỗi ở file đã sửa
```

QA trên clip thật `out/deliveries/havana_donna_set/clips/clip1.mp4` (720×1280, 24fps, 8.000s):
9 gate → 5 pass / 3 warn / 1 skip, chạy 3.7s. Ba cảnh báo đều là lỗi thật của clip đó:

- `resolution_ok` — 720×1280 phải phóng 1.5× lên 1080×1920.
- `no_baked_ui` — board UI nằm trong 1.3s đầu.
- `hook_clean` — board phủ 1.3s, gần trọn hook 2.0s ⇒ cắt bỏ là mất hook.

---

## 5. Quyết định thiết kế đáng ghi lại

**D-002 — canvas giữ 1080×1920 dù Flow trả 720×1280.** Không hạ composition xuống theo nguồn,
vì đổi canvas là đổi hợp đồng với toàn bộ delivery đã xuất. Thay vào đó QA cảnh báo hệ số upscale
1.5× để người dựng biết mất nét ở đâu.

**D-003 — renderer tất định, agent chỉ thêm `custom_hint`.** Nếu agent được viết lại câu, mỗi lần
chạy ra một prompt khác nhau và gate round-trip không còn ý nghĩa. Đổi lại, agent mất quyền sáng
tạo — nhưng prompt video Lookbook cần ổn định hơn là hoa mỹ.

**D-004 — chỉ văn xuôi có thứ tự sống sót sanitizer.** Ba định dạng nhãn thời gian đã thử; chỉ
`For the first N seconds … From the Ath to the Bth second … In the final N seconds` đi qua
`sanitize_video_prompt(aggressive=False)` byte-for-byte. Đây là lý do prompt trông "văn xuôi" chứ
không phải bảng timeline — bảng sẽ bị xoá trước khi tới Flow.

**QA không nối vào `result.warnings`.** README đã có bảng QA riêng, và `_clip_manifest_entry` đã
cảnh báo board UI theo cách của nó. Nối thêm thì mỗi lỗi hiện hai lần. Gate chưa đo được nằm
trong `qa_summary.skipped` thay vì làm nhiễu danh sách cảnh báo.

---

## 6. Lỗi gặp trong lúc làm (để lần sau không lặp)

- **`ffmpeg -ss 1e6` trả 0 khung, không báo lỗi.** `gate_chain_match` ban đầu dùng cách này để
  lấy khung cuối, nên gate im lặng rơi vào `skip` dù file đọc được. Sửa bằng `-sseof -0.1`
  (`_grab_last_frame`).
- **`freezedetect -40dB` báo nhầm** chuyển động rất chậm là đứng yên. `-50dB` mới đúng.
- **`scdet threshold=10` bắt nhầm** pha đổi tư thế. Dùng 12.
- **`str.find` trên instruction của agent có thể khớp vào skill markdown** thay vì context động,
  vì skill có chứa chính các chuỗi `clips[].beats`. Phải dùng marker riêng (`Clip đang viết`).

---

## 7. Còn mở

1. **QA chỉ chạy lúc export delivery.** Muốn thấy ngay trong Flow Bench thì gọi
   `evaluate_clip` ở endpoint job-status và trả `qa.status` về FE.
2. **`chain_match` chưa từng chạy trên cặp clip1→clip2 thật.** Repo chỉ có clip1; ngưỡng 0.90
   mới kiểm bằng fixture tổng hợp.
3. **5 test đỏ baseline** vẫn đỏ — sửa test hoặc bỏ entry `9:16: 2` khỏi `accounts_pool.json`.

---

## 8. File thay đổi

| File | +/− | Nội dung |
|:--|--:|:--|
| `src/Workflows/raw_video_qa.py` | +657 | **mới** — 9 gate QA |
| `src/Workflows/motion_prompt.py` | +272 | **mới** — renderer beats → prose |
| `tests/test_raw_video_qa.py` | +407 | **mới** |
| `tests/test_motion_prompt.py` | +198 | **mới** |
| `tests/test_prompt_agent_context.py` | +153 | **mới** |
| `tests/test_script_beats.py` | +144 | **mới** |
| `tests/test_node_options_script.py` | +68 | **mới** |
| `src/Workflows/script_contract.py` | +98/−1 | `BeatSpec`, `_validate_beats()` |
| `src/Workflows/delivery.py` | +77 | `_attach_clip_qa`, `qa_summary`, bảng README |
| `src/Workflows/prompt_lint.py` | +60/−4 | ngân sách 120/40, bỏ qua mệnh đề phủ định |
| `src/Workflows/prompt_agent.py` | +60 | `_beat_lines()`, cảnh báo thiếu `clip_id` |
| `src/Workflows/media_service.py` | +32 | `node_options()` trả `script` |
| `configs/lookbook_script.json` | +57/−2 | goal + 3 beat + negative mỗi clip |
| `prompt-skills/lookbook-video-prompter.md` | +83/−27 | §4–§7 viết lại |
| `web/src/components/CanvasDrawer.tsx` | +50/−2 | select clip, call site 3 |
| `web/src/hooks.ts` | +38 | `useScriptClips()` |
| `web/src/types.ts` | +29 | `clipId`, `ScriptClipOption` |
| `web/src/components/CanvasPanel.tsx` | +25/−1 | `SCRIPT_PATH`, `clipRoleOf()` |
| `configs/lookbook_script.schema.json` | +38 | schema beats/negative |
| `tests/test_prompt_skills_contract.py` | +71/−5 | khoá skill == renderer output |
