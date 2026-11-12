---
name: merge2main
description: Land the current Delta worktree onto `main` after the user explicitly confirms the task is done with /merge2main — fetch, separate real changes from runtime-mutated tracked files, run the full gate suite, commit, push, then verify the remote. Use for the flow-reverse repo, where real runs started by run.ps1 rewrite tracked config state that must never be committed.
disable-model-invocation: true
---

# merge2main

Đưa thay đổi của worktree hiện tại lên `main`, **chỉ khi người dùng gõ `/merge2main`**.

Skill này tắt tự gọi từ model (`disable-model-invocation: true`): merge vào `main` là hành động
không thể lùi, nên người dùng là bên bấm còi. Nếu người dùng nói "ok merge đi" bằng lời thường,
đó vẫn là uỷ quyền hợp lệ — cứ merge, không cần skill này.

## 0. Cổng vào — kiểm tra trước khi làm bất cứ gì

Dừng lại và hỏi nếu bất kỳ điều nào dưới đây không đúng:

1. Người dùng **đã xác nhận task hoàn thành**. "Chạy test đi" hay "sửa nốt cái này" không phải
   là xác nhận hoàn thành.
2. Việc cần merge là **thay đổi thật của task**, không phải trạng thái do một lần chạy sinh ra
   (xem §2 — đây là cái bẫy chính của repo này).
3. Gate ở §3 xanh **trên đúng cây sẽ được commit**.

## 1. Xác lập sự thật của remote

Luôn fetch trước; đừng tin `origin/main` đang cache trong máy.

```bash
git fetch origin
git --no-optional-locks rev-parse --abbrev-ref HEAD      # phải là một nhánh làm việc, không phải detached
git --no-optional-locks log --oneline origin/main..HEAD  # commit sẽ đẩy lên
git --no-optional-locks log --oneline HEAD..origin/main  # commit cần kéo về trước (nếu có)
```

Nếu `HEAD..origin/main` không rỗng thì `main` đã tiến: **rebase lên trước**, đừng push chồng.

```bash
git -c core.editor=true rebase origin/main
```

Xung đột ⇒ dừng, báo người dùng, để họ quyết định. Không tự "giải" xung đột bằng cách chọn phe.

## 2. Tách thay đổi thật khỏi rác do lần chạy sinh ra (bắt buộc)

Repo này coi `main` là nguồn sự thật của **mã**, còn các file sau bị chính pipeline ghi lại mỗi
lần chạy thật bằng `run.ps1`. Chúng **có tracked** (nên hiện trong `git status`), nhưng **không
thuộc về commit của task nào**:

| File | Ai ghi | Xử lý khi merge |
| :--- | :--- | :--- |
| `configs/project_media_cache.json` | `src/Workflows/project_media_registry.py` — cache `media_id` + alias sau mỗi lần upload ảnh lên Flow | **Không commit.** Chứa dấu vết phiên của account thật |
| `configs/accounts_pool.json` | Người dùng bật/tắt profile trong tab Pool | **Không commit**, trừ khi chính task là sửa file này |

Đã gitignore sẵn, không cần bàn: `out/`, `traces/`, `browser_vault/`, `web/dist/`, `configs/reference_media_cache.json`.

Cách làm:

```bash
git --no-optional-locks status --short
```

Với mỗi file là trạng thái-runtime ở bảng trên: **để nguyên trong working tree, không `git add`**.
Nếu task thật sự cần đổi `accounts_pool.json`, nói rõ với người dùng rằng commit này sẽ mang cấu
hình profile của họ lên `main`, rồi mới thêm.

Rà lại lần cuối trước khi commit — staged phải đúng bằng danh sách sẽ báo ở §4:

```bash
git --no-optional-locks diff --cached --stat
git --no-optional-locks diff --cached --name-only
```

## 3. Gate — chạy trên đúng cây sắp commit

Chạy cả bốn, từ thư mục gốc repo. Bốn lệnh này là gate chuẩn của repo, không thay bằng lệnh khác:

```bash
python -m pytest tests -q          # backend; kỳ vọng: toàn bộ pass, chỉ skip có lý do
npx --prefix web tsc --noEmit -p web/tsconfig.json   # hoặc: cd web && npm run typecheck
npm --prefix web test              # node --test + verify-snippets
npm --prefix web run build         # bundle phải build được
```

Ghi lại **con số thật** của `pytest` (ví dụ "490 passed, 11 skipped") để đưa vào báo cáo cuối.
Gate đỏ ⇒ dừng, báo lỗi, **không commit, không push**.

## 4. Commit — **một commit duy nhất**

Mặc định: **gộp tất cả thay đổi của task vào MỘT commit**. Người dùng không cần lịch sử git
đẹp, chỉ cần lịch sử **đủ hiểu**. Một commit + message rõ ràng là đủ.

Không tách theo chủ đề, không `git reset --soft` để chia lại, không amend nhiều lần. Tách
commit là thứ đã làm một lần merge mất hơn nửa tiếng và còn tạo ra lỗi phụ (file bị xoá
sống lại trên đĩa sau chuỗi `reset`). Đừng lặp lại.

Ngoại lệ duy nhất — tách khi người dùng **yêu cầu rõ** trong lượt đó. Và **không bao giờ
squash commit có sẵn của người khác** trên nhánh.

Commit message theo kiểu đang dùng trong repo (`type(scope): mô tả`, tiếng Anh, mệnh lệnh cách),
phần thân nêu **vấn đề gì và vì sao sửa**, không liệt kê từng file:

```bash
git -c core.editor=true commit -m "fix(images): stop losing money to Flow's filter" -m "<why>"
```

Trình bày gọn trước khi push: nhánh, file staged, và 4 kết quả gate. Nếu người dùng đã nói
"merge luôn, đừng hỏi lại" thì bỏ bước chờ — push thẳng.

## 5. Land và kiểm chứng

```bash
git push origin HEAD:main
```

Không bao giờ `--force`, không bao giờ `--force-with-lease` lên `main`. Bị từ chối vì
non-fast-forward ⇒ quay lại §1 (fetch + rebase), đừng ép.

Nếu GitHub chặn push (branch protection) ⇒ mở PR thay vì tìm cách lách:

```bash
gh pr create --base main --head "$(git rev-parse --abbrev-ref HEAD)" --fill
```

Xác minh **trên remote**, không phải qua niềm tin vào lệnh push:

```bash
git ls-remote origin refs/heads/main     # SHA phải bằng HEAD vừa push
git --no-optional-locks rev-parse HEAD
```

## 6. Báo cáo và dọn dẹp

- **Tắt những gì mình đã bật.** Nếu trong lượt có bật `run.ps1 start` / `restart` (browser +
  WebUI) thì trước khi kết thúc phải chạy ``.\run.ps1 stop`` — trừ khi người dùng nói rõ họ
  đang cần dùng tiếp. Một browser CloakBrowser sống chiếm ~1.6 GB RAM (đo 2026‑11‑12) và không
  tự tắt. Kiểm chứng bằng số, không đoán:

  ```powershell
  (Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object).Count   # kỳ vọng 0
  ```

- Nêu SHA đã land, kèm kết quả gate thật đã chạy (và nói rõ gate nào **không** chạy được).
- Nếu đây là một lần merge do người dùng gọi, xuất đúng một khối `<land-result>` theo skill
  `report-landed`; link commit/target chỉ dùng giá trị đọc được từ git, không tự ghép.
- Nhắc người dùng checkout cá nhân cần `git pull --rebase` — xem §7.
- File runtime ở §2 vẫn nằm trong working tree: **để nguyên**, đó là trạng thái đang chạy của họ.

## 7. Bẫy đã gặp thật ở repo này

- **Tách commit làm chậm gấp nhiều lần và sinh lỗi phụ.** Lần land 2026‑11‑12 mất hơn nửa
  tiếng cho một thay đổi lẽ ra vài phút, vì chia 4 commit theo chủ đề rồi phát hiện chia sai
  (`agent.py` lọt nhóm sau, file try-on lọt commit sheet) nên phải amend hai lần; chuỗi
  `git reset --soft` còn làm file đã xoá sống lại trên đĩa (chỉ khác CRLF) và tốn thêm lượt
  kiểm tra. → **Một commit, xong.** Xem §4.
- **Chạy gate SAU khi staged xong, không phải trước.** Lần đó gate bị chạy hai lượt vì cây
  còn đổi sau lượt đầu. Thứ tự đúng: stage → gate → commit → push.
- **Checkout cá nhân `D:\Dev\rev-flow` có thể đã lệch `origin/main`.** Quan sát 2026‑11‑12:
  `main` ở đó có 2 commit chưa đẩy (`21d1342`, `ab5087d`) đồng thời thiếu 3 commit của `origin/main`
  (`6bc4d30`, `89caae4`, `5b56779`); merge-base là `d640f18`. Land thêm từ worktree sẽ làm khoảng
  lệch rộng ra. Kiểm tra bằng
  `git -C D:/Dev/rev-flow rev-list --left-right --count main...origin/main` và **nói rõ** con số đó
  cho người dùng thay vì lặng lẽ push.
- **Worktree Delta của thread này đứng ngay trên `main`.** Nhiều thread cùng đứng trên `main` thì
  công việc của thread khác phải kéo về bằng `merge_worktrees` (công cụ Delta), **không** phải
  `git merge` giữa các checkout — hai cây đó không chia sẻ index.
- **`run.ps1` tự `npm run build` khi `web/dist` cũ.** Build lại UI không tạo thay đổi cần commit
  (`web/dist/` đã gitignore); đừng đưa `web/dist` vào commit.
- **Đừng land khi còn job Flow đang chạy.** `configs/project_media_cache.json` sẽ tiếp tục bị ghi
  sau khi commit, và bạn không biết cây lúc push có đúng như lúc test hay không. Kiểm tra
  `http://127.0.0.1:4000/api/status` → `queue_depth` / `current_job_id` phải trống.
- **Không land thay đổi đang dở của người dùng.** Nếu `git status` có file bạn không tạo ra và
  người dùng chưa nhắc tới, dừng và hỏi trước khi `git add` bất cứ thứ gì.
