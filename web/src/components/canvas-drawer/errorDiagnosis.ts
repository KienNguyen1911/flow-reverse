import { FALLBACK_LIMITS } from "../../hooks";
import type { JobEvent } from "../../types";

export interface ErrorDiagnosis {
  code: string;
  title: string;
  explanation: string;
  fixHint: string;
}

/** True when the latest log line is an anti-abuse retry countdown (Task 3). */
export function isWaitingRetry(events?: JobEvent[] | null): boolean {
  if (!events || events.length === 0) return false;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.kind === "retry") {
      return /Đang chờ|trước khi thử lại/.test(e.message || "");
    }
    if (e.kind === "info" && /Hết thời gian chờ/.test(e.message || "")) return false;
    if (e.kind === "done" || e.kind === "error") return false;
  }
  return false;
}

export function diagnoseError(
  reason: string | null | undefined,
  maxPrompt: number = FALLBACK_LIMITS.max_prompt_chars,
): ErrorDiagnosis {
  const r = (reason || "").trim();
  const lower = r.toLowerCase();
  const fmt = maxPrompt.toLocaleString("vi-VN");

  if (
    lower.includes("prominent_people_filter") ||
    lower.includes("người nổi tiếng") ||
    lower.includes("prominent")
  ) {
    return {
      code: "PROMINENT_PEOPLE_FILTER",
      title: "Bộ lọc nhận diện người nổi tiếng của Google",
      explanation:
        "Google Flow từ chối xử lý vì phát hiện khuôn mặt trong ảnh tham chiếu (hoặc tên nhân vật trong prompt) có nét tương đồng với người nổi tiếng hoặc nhân vật công chúng được bảo vệ bản quyền.",
      fixHint:
        "1. Thay ảnh tham chiếu bằng hình ảnh người mẫu khác (hoặc đổi góc mặt, làm mờ nhẹ).\n2. Kiểm tra lại prompt và loại bỏ tên người nổi tiếng, ca sĩ, diễn viên hoặc từ khóa thương hiệu.",
    };
  }

  if (
    lower.includes("unusual_activity") ||
    lower.includes("chống lạm dụng") ||
    lower.includes("permission_denied")
  ) {
    return {
      code: "UNUSUAL_ACTIVITY",
      title: "Hệ thống chống lạm dụng của Google từ chối (tạm thời)",
      explanation:
        "Google Flow đánh giá phiên đăng nhập của browser này có dấu hiệu bất thường (tốc độ, fingerprint hoặc IP) nên chặn ngay khi submit. Lỗi này không mất credit và thường chỉ là tạm thời.",
      fixHint:
        "1. Node đã tự động thử lại 2 lần (Ảnh: 10s/20s, Video: 30s/60s) — xem tab Nhật ký (Logs).\n2. Nếu vẫn lỗi: gắn proxy riêng cho browser trong tab Tài khoản/Pool để đổi IP, hoặc thêm account khác vào pool.\n3. Giảm số browser chạy song song (M_RAM) nếu đang chạy batch lớn, rồi thử lại sau vài phút.",
    };
  }

  if (lower.includes("circuit_breaker") || lower.includes("circuit breaker") || lower.includes("anti-abuse")) {
    return {
      code: "CIRCUIT_BREAKER_ACTIVE",
      title: "Tạm dừng an toàn (Anti-Abuse Cooldown)",
      explanation:
        "Hệ thống tự động kích hoạt cơ chế Circuit Breaker sau khi tài khoản Google Flow liên tục phản hồi từ chối hoặc lỗi bảo vệ, nhằm ngăn chặn nguy cơ tài khoản bị khóa vĩnh viễn.",
      fixHint:
        "Chờ vài phút để hết thời gian cooldown (hiển thị trên thông báo lỗi), hoặc chuyển sang sử dụng profile/tài khoản khác trong tab Tài khoản/Pool.",
    };
  }

  if (lower.includes("composer không có") || lower.includes("pageinteractionerror") || lower.includes("selector")) {
    return {
      code: "PAGE_INTERACTION_ERROR",
      title: "Không tìm thấy phần tử tải ảnh trên trang Flow",
      explanation:
        "Kịch bản trình duyệt không tìm thấy nút tải ảnh lên giao diện Google Flow. Có thể trang web chưa load hoàn tất hoặc cấu trúc giao diện vừa cập nhật.",
      fixHint:
        "1. Kiểm tra cửa sổ Chrome đang chạy tại cổng 4022 để xem trang web có đang mở bình thường không.\n2. Tải lại trang Flow trong trình duyệt hoặc khởi động lại profile.",
    };
  }

  if (lower.includes("unsafe_generation") || lower.includes("safety") || lower.includes("chính sách")) {
    return {
      code: "UNSAFE_GENERATION",
      title: "Vi phạm bộ lọc an toàn nội dung của Google",
      explanation:
        "Google Flow đánh giá prompt hoặc ảnh đầu vào không vượt qua tiêu chuẩn an toàn nội dung (nhạy cảm, bạo lực, hoặc không phù hợp chính sách AI).",
      fixHint:
        "Điều chỉnh prompt sang các từ ngữ trung tính, mô tả trang phục và bối cảnh chuẩn mực hơn.",
    };
  }

  // Backend trả câu tiếng Việt ("Tham số không hợp lệ: prompt: …") từ
  // validation_exception_handler, nên khớp theo tiếng Anh là trượt và rơi xuống
  // EXECUTION_ERROR — người dùng bị hướng dẫn đi kiểm tra mạng dù lỗi nằm ở chỗ khác.
  if (lower.includes("từ google") || lower.includes("từ google:") || (lower.includes("invalid_argument") && lower.includes("[3]"))) {
    return {
      code: "VALIDATION_ERROR",
      title: "Google Flow từ chối tham số yêu cầu",
      explanation:
        "Google Flow phản hồi mã lỗi INVALID_ARGUMENT ([3]). Nguyên nhân: số lượng thẻ ảnh tham chiếu (@mention chip) bị lặp lại quá nhiều lần hoặc vượt giới hạn 3 tham chiếu cho phép của Google Flow. Yêu cầu chưa được xử lý nên không mất credit.",
      fixHint:
        "1. Hệ thống đã tự động giới hạn chỉ chèn tối đa 1 thẻ @mention chip cho mỗi ảnh tham chiếu, các vị trí nhắc lại trong prompt sẽ giữ nguyên dạng text.\n2. Bấm 'Thử chạy lại ngay' để tạo lại.",
    };
  }

  if (
    lower.includes("validation") ||
    lower.includes("422") ||
    lower.includes("invalid_argument") ||
    lower.includes("tham số không hợp lệ") ||
    lower.includes("tham so khong hop le") ||
    lower.includes("should have at least") ||
    lower.includes("string should have")
  ) {
    return {
      code: "VALIDATION_ERROR",
      title: "Tham số đầu vào không hợp lệ",
      explanation:
        `Dữ liệu gửi lên server không đúng định dạng hoặc vượt quá giới hạn cho phép (prompt rỗng, quá ${fmt} ký tự, tỷ lệ khung hình, seed,...). Lỗi này phát sinh ngay tại app, chưa gửi gì lên Google Flow nên không mất credit.`,
      fixHint:
        `1. Prompt rỗng là nguyên nhân phổ biến nhất — nhập prompt hoặc bấm AI Prompt trên node rồi chạy lại.\n2. Prompt tối đa ${fmt} ký tự; chọn tỷ lệ khung hình đã được xác thực.`,
    };
  }

  if (lower.includes("không tìm thấy file") || lower.includes("filenotfound")) {
    return {
      code: "FILE_NOT_FOUND",
      title: "Không tìm thấy file nguồn",
      explanation:
        "File ảnh hoặc video đầu vào không tồn tại trên ổ cứng hoặc đường dẫn đã thay đổi.",
      fixHint:
        "Hãy chạy lại node nguồn trước đó để tạo ra file kết quả mới, hoặc kiểm tra file upload.",
    };
  }

  return {
    code: "EXECUTION_ERROR",
    title: "Lỗi thực thi",
    explanation: r || "Quá trình thực thi gặp sự cố không xác định.",
    fixHint:
      "Kiểm tra trạng thái kết nối mạng, tài khoản Google Flow và xem chi tiết nhật ký sự kiện bên dưới.",
  };
}
