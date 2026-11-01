# Turbo agent — thiết kế dựa trên nghiên cứu

## Mục tiêu

`turbo` là một **primary agent** (chọn được cạnh Build và Plan) dành cho long-task: công việc kéo dài nhiều
bước, nhiều file, có thể vượt qua nhiều context window. Agent này không chỉ "chạy nhanh hơn" mà thay đổi cách
làm việc:

- giữ trạng thái bền vững ngoài context (ledger),
- tiến bộ từng feature một, có kiểm chứng,
- dùng subagent để bảo vệ context và mở rộng độ phủ,
- không tuyên bố hoàn thành khi chưa có bằng chứng.

File cấu hình: `.opencode/agents/turbo.md`.

## Nguồn tham khảo

| Nguồn | Điều được áp dụng |
| --- | --- |
| [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Orchestrator-workers cho tác vụ không đoán trước được số bước; ưu tiên đơn giản, chỉ tăng độ phức tạp khi có lợi ích rõ; agent cần ground truth từ môi trường sau mỗi bước. |
| [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | Brief giao việc phải có mục tiêu, định dạng đầu ra, công cụ/nguồn, ranh giới; scale effort theo độ phức tạp; multi-agent tốn khoảng 15× token so với chat; ghi output lớn ra filesystem và chỉ trả về tham chiếu; lỗi tích lũy nên cần checkpoint và resume. |
| [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Compaction, structured note-taking và sub-agent architecture; subagent trả về bản tóm tắt 1.000–2.000 token; context là tài nguyên hữu hạn. |
| [Anthropic — Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | Initializer agent tạo feature list + progress file + git commit đầu tiên; mỗi session làm một feature; verify end-to-end trước khi đánh dấu `passes`; dùng JSON cho trạng thái dễ thay đổi; đọc git log và progress khi bắt đầu session. |
| [Cognition — Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) | Hai nguyên tắc: chia sẻ đầy đủ context và "actions carry implicit decisions". Không cho nhiều subagent sửa song song các phần phụ thuộc nhau; ưu tiên luồng tuyến tính cho công việc code có ràng buộc. |
| [OpenCode V2 — Agents](https://opencode.ai/v2/docs/agents) | Cú pháp agent Markdown, `mode`, `steps`, `permissions`, `subagent` permission, built-in `general` / `explore`. |
| [OpenCode V2 — Permissions](https://opencode.ai/v2/docs/permissions) | Thứ tự rule "last match wins", base policy allow, cách chặn các lệnh không thể đảo ngược. |

## Các quyết định thiết kế

### 1. Là primary agent, không phải subagent

Turbo cần tự điều phối và giữ vai trò "lead". Nếu là subagent, nó sẽ bị giới hạn bởi agent cha và không hiển thị
như một mode làm việc độc lập. `mode: primary` cho phép chọn Turbo giống Build/Plan.

### 2. Ledger thay vì dựa vào trí nhớ hội thoại

Bài học từ harness cho long-running agent: mỗi session mới bắt đầu với context trống. Turbo tạo
`.turbo/<slug>/` gồm `spec.md`, `features.json`, `progress.md`, `decisions.md`, `handoff.md`.

`features.json` được chọn thay vì Markdown vì nghiên cứu của Anthropic chỉ ra model ít có xu hướng sửa/xóa JSON
một cách tùy tiện hơn. Trạng thái `passes` chỉ được đổi sau khi verify.

### 3. Một feature mỗi vòng lặp

Đây là biện pháp chống lại hai failure mode phổ biến: one-shot quá nhiều việc rồi hết context giữa chừng, và
tuyên bố hoàn thành sớm khi thấy một phần đã chạy.

### 4. Subagent chỉ cho việc tách rời được

Cognition cảnh báo multi-agent dễ vỡ khi các agent đưa ra quyết định ngầm xung đột. Vì vậy Turbo:

- giao **điều tra / khảo sát** cho `explore` / `explorer`,
- giao **implementation độc lập trên tập file rời** hoặc **verification độc lập** cho `general`,
- không chạy song song các chỉnh sửa phụ thuộc nhau,
- không để chính agent implement tự verify lần cuối,
- luôn gửi brief đầy đủ context và hợp đồng đầu ra.

### 5. Giới hạn fan-out và ngân sách

Tối đa 5 subagent song song, ưu tiên 1–2 cho việc tập trung. Multi-agent tốn token gấp nhiều lần; chỉ dùng khi
giá trị của task đủ lớn và các nhánh thực sự độc lập.

### 6. Cổng kiểm chứng và quyền hạn

- `steps: 100` cho phép chạy dài trong một lượt nhưng vẫn có điểm dừng.
- Các lệnh không thể đảo ngược (`git push`, `git reset --hard`, `git clean`, `rm -rf`) được đặt `ask`.
- Turbo dừng và hỏi khi yêu cầu mâu thuẫn, thiếu quyền, hoặc lỗi lặp lại 3 lần.

## Cách sử dụng

1. Trong TUI, chọn agent **Turbo** (ngang hàng Build/Plan).
2. Giao mục tiêu ở mức outcome, ví dụ:
   - "Triển khai xong module X theo `docs/api_specs/...`, có test và verify end-to-end."
   - "Điều tra và hợp nhất hai pipeline Y/Z, không phá vỡ hành vi hiện tại."
3. Turbo sẽ tạo ledger (nếu là long-task), chọn feature đầu tiên và bắt đầu.
4. Theo dõi tiến độ trong `.turbo/<slug>/progress.md`; có thể dừng và quay lại bất kỳ lúc nào — session sau sẽ
   đọc ledger và tiếp tục.

## Khi nào không nên dùng Turbo

- Việc nhỏ, một file, xong trong vài bước: dùng Build sẽ nhanh và rẻ hơn.
- Việc cần thay đổi kiến trúc lớn hoặc quyết định sản phẩm: dùng Plan trước, rồi Turbo để triển khai.
- Việc mà mọi bước đều phụ thuộc tuần tự vào nhau: Turbo vẫn làm được nhưng lợi ích của subagent sẽ thấp.

## Ghi chú vận hành

- Ledger nằm trong repo để session sau và đồng đội đọc được. Nếu không muốn commit, thêm `.turbo/` vào
  `.gitignore` và chấp nhận mất khả năng handoff qua git.
- Có thể chỉnh `steps` hoặc danh sách quyền trong frontmatter của `.opencode/agents/turbo.md`.
- Agent dùng model của session hiện tại; không gán cứng model để tránh lệch với cấu hình provider.
- Turbo commit theo từng feature để làm checkpoint (theo khuyến nghị của Anthropic). Nếu không muốn agent tự commit,
  nói rõ ngay từ đầu; khi đó nó ghi checkpoint vào ledger thay vì commit.
