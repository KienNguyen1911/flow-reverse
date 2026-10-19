import { useState } from "react";
import {
  BookOpen,
  CheckCircle,
  Clock,
  Cpu,
  Coins,
  Flask,
  Images,
  Keyboard,
  ShieldCheck,
  Sparkle,
  X,
} from "@phosphor-icons/react";
import { Btn, IconBtn } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
}

type TabKey = "credit" | "batch" | "safety" | "shortcuts";

export function GuideModal({ open, onClose }: Props) {
  const [tab, setTab] = useState<TabKey>("credit");

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative flex max-h-[88vh] w-full max-w-2xl flex-col rounded-panel border border-line bg-panel shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line2 bg-panel2 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-8 place-items-center rounded-ctl bg-acc/15 text-acc">
              <BookOpen size={18} weight="bold" />
            </div>
            <div>
              <h2 className="text-[15.5px] font-bold text-fg">Hướng dẫn & Quy chuẩn Vận hành</h2>
              <p className="text-[11.5px] text-mut">
                Quy tắc tính credit, tạo ảnh hàng loạt và điều phối trình duyệt CloakBrowser
              </p>
            </div>
          </div>
          <IconBtn label="Đóng" onClick={onClose}>
            <X size={16} />
          </IconBtn>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-line2 bg-panel px-5 pt-2 gap-1 overflow-x-auto slim-scroll">
          <button
            onClick={() => setTab("credit")}
            className={`flex items-center gap-2 border-b-2 px-3 py-2 text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
              tab === "credit"
                ? "border-acc text-acc"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <Coins size={15} />
            <span>Credit & Chế độ Chạy</span>
          </button>
          <button
            onClick={() => setTab("batch")}
            className={`flex items-center gap-2 border-b-2 px-3 py-2 text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
              tab === "batch"
                ? "border-acc text-acc"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <Images size={15} />
            <span>Chế độ Batch & Pool</span>
          </button>
          <button
            onClick={() => setTab("safety")}
            className={`flex items-center gap-2 border-b-2 px-3 py-2 text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
              tab === "safety"
                ? "border-acc text-acc"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <ShieldCheck size={15} />
            <span>Lưu ý Trình duyệt & An toàn</span>
          </button>
          <button
            onClick={() => setTab("shortcuts")}
            className={`flex items-center gap-2 border-b-2 px-3 py-2 text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
              tab === "shortcuts"
                ? "border-acc text-acc"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <Keyboard size={15} />
            <span>Mẹo & Phím tắt</span>
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-[12.5px] leading-relaxed text-dim slim-scroll">
          {tab === "credit" && (
            <div className="space-y-4">
              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <Sparkle size={16} className="text-acc" weight="fill" />
                  <span>Quy tắc trừ Credit của Google Flow</span>
                </div>
                <ul className="space-y-2 list-disc list-inside text-dim">
                  <li>
                    <strong className="text-fg">Tạo ảnh thành công:</strong> Mỗi ảnh hoàn thành tốn khoảng <span className="font-semibold text-acc">~1 credit</span> trừ trực tiếp vào hạn mức gói của tài khoản Google.
                  </li>
                  <li>
                    <strong className="text-fg">Bị từ chối (Rejected):</strong> Nếu prompt kích hoạt bộ lọc an toàn của Google, hệ thống ghi nhận mã phản hồi lỗi và <span className="font-semibold text-ok">hoàn toàn 0 credit</span> (không bị trừ).
                  </li>
                  <li>
                    <strong className="text-fg">Thất bại kỹ thuật:</strong> Nếu request bị nghẽn mạng hoặc timeout trước khi Google xử lý, credit sẽ không bị trừ.
                  </li>
                </ul>
              </div>

              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <Flask size={16} className="text-acc" />
                  <span>Chế độ Thử nghiệm (Dry-run)</span>
                </div>
                <p>
                  Khi bấm <strong className="text-fg">Dry-run</strong> hoặc <strong className="text-fg">Batch dry-run</strong>:
                </p>
                <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                  <li>Hệ thống chạy toàn bộ pipeline: xác thực dự án, kiểm tra token phiên, tải ảnh tham chiếu i2i, mô phỏng hàng đợi Account Pool.</li>
                  <li><strong className="text-acc">Luôn tiêu tốn 0 credit</strong> vì request dừng ngay trước khi gửi lệnh tính phí lên máy chủ Google.</li>
                  <li>Rất hữu ích để kiểm tra cú pháp prompt, độ ổn định của profile trước khi chạy thật.</li>
                </ul>
              </div>
            </div>
          )}

          {tab === "batch" && (
            <div className="space-y-4">
              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <Images size={16} className="text-acc" />
                  <span>Cú pháp & Quy chuẩn Batch Prompt</span>
                </div>
                <p>
                  Trong chế độ Batch, bạn có thể nhập nhiều prompt cùng một lúc:
                </p>
                <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                  <li>Mỗi dòng văn bản tương ứng với <strong className="text-fg">1 ảnh độc lập</strong>. Dòng trống được tự động bỏ qua.</li>
                  <li>Hỗ trợ tối đa <strong className="text-fg">300 ảnh/batch</strong> trong một lượt chạy.</li>
                  <li>Mỗi dòng có độ dài tối đa 2000 ký tự.</li>
                </ul>
              </div>

              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <Cpu size={16} className="text-acc" />
                  <span>Công thức Phân bổ Tải & Tiết kiệm RAM</span>
                </div>
                <p>
                  Hệ thống phân bổ tài khoản song song theo công thức:
                </p>
                <div className="my-2 rounded bg-panel px-3 py-2 font-mono text-[12px] text-acc border border-line2">
                  N_alloc = min(N, M_RAM, ceil(J / Q_target))
                </div>
                <ul className="space-y-1.5 list-disc list-inside text-dim">
                  <li><strong className="text-fg">J:</strong> Tổng số ảnh trong batch.</li>
                  <li><strong className="text-fg">Q_target:</strong> Ngưỡng ảnh trên mỗi account (mặc định 25 ảnh/account).</li>
                  <li><strong className="text-fg">M_RAM:</strong> Giới hạn số trình duyệt chạy đồng thời (mặc định 4) để chống quá tải RAM.</li>
                  <li><strong className="text-fg">Cơ chế Standby:</strong> Các tài khoản chưa đến lượt hoặc rảnh rỗi sẽ luôn được đóng trình duyệt để giải phóng 100% RAM. Khi cần phân việc, hệ thống mới tự động đánh thức (wake).</li>
                </ul>
              </div>

              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-1">
                  <CheckCircle size={16} className="text-acc" />
                  <span>Ảnh tham chiếu Image-to-Image (i2i)</span>
                </div>
                <p className="mt-1">
                  Điền đường dẫn tệp ảnh cục bộ (ví dụ: <code className="font-mono text-acc">out/outputs/.../shot_001.jpg</code>). Hệ thống sẽ tự động chuyển tất cả các dòng prompt trong batch sang chế độ tham chiếu i2i, giúp duy trì diện mạo nhân vật và phong cách hình ảnh xuyên suốt.
                </p>
              </div>
            </div>
          )}

          {tab === "safety" && (
            <div className="space-y-4">
              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <Clock size={16} className="text-warn" />
                  <span>Nguyên tắc Không can thiệp Tab Trình duyệt</span>
                </div>
                <p>
                  Khi một tác vụ (tạo ảnh hoặc batch) đang chạy:
                </p>
                <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                  <li>Playground kết nối và điều khiển trực tiếp tab Flow trong <strong className="text-fg">CloakBrowser</strong> qua giao thức CDP.</li>
                  <li><strong className="text-warn">Không click chuột, reload hoặc chuyển hướng tab Flow đó</strong> bằng tay trong lúc bot đang thao tác để tránh xung đột session và làm hỏng request.</li>
                  <li>Sau khi hoàn thành tạo ảnh, bạn có thể tự do mở xem hoặc tải ảnh bình thường.</li>
                </ul>
              </div>

              <div className="rounded-ctl border border-line2 bg-panel2 p-4">
                <div className="flex items-center gap-2 text-fg font-bold mb-2">
                  <ShieldCheck size={16} className="text-ok" />
                  <span>Bộ ngắt Mạch Bảo vệ Tài khoản (Circuit Breaker)</span>
                </div>
                <p>
                  Nhằm bảo vệ tài khoản khỏi bị Google gắn cờ spam hoặc tạm khóa:
                </p>
                <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                  <li>Nếu gặp lỗi <strong className="text-fg">429 (Too Many Requests)</strong>: Tài khoản sẽ tự động kích hoạt Cooldown và tạm dừng trong vài phút.</li>
                  <li>Nếu gặp lỗi <strong className="text-fg">403 (Hết phiên/Auth expired)</strong>: Hệ thống đánh dấu tài khoản cần đăng nhập lại thay vì gửi lặp lại gây nghi vấn.</li>
                  <li>Bạn có thể mở modal <strong className="text-fg">Quản lý Account</strong> bất kỳ lúc nào để kiểm tra chi tiết trạng thái hoặc reset cooldown.</li>
                </ul>
              </div>
            </div>
          )}

          {tab === "shortcuts" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
                <span>Chạy tạo ảnh nhanh khi đang nhập Prompt</span>
                <kbd className="rounded border border-line2 bg-panel px-2 py-1 font-mono text-[11px] text-fg">
                  Ctrl + Enter
                </kbd>
              </div>
              <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
                <span>Mở / Đóng popup hướng dẫn này</span>
                <kbd className="rounded border border-line2 bg-panel px-2 py-1 font-mono text-[11px] text-fg">
                  Esc
                </kbd>
              </div>
              <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
                <span>Quản lý hồ sơ trình duyệt & tài khoản Google</span>
                <span className="text-[12px] text-acc font-semibold">
                  Nút "Quản lý Account" trên thanh TopBar
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end border-t border-line2 bg-panel2 px-5 py-3">
          <Btn variant="primary" onClick={onClose}>
            Đã hiểu
          </Btn>
        </div>
      </div>
    </div>
  );
}
