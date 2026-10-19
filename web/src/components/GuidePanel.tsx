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
} from "@phosphor-icons/react";

type TabKey = "credit" | "batch" | "safety" | "shortcuts";

export function GuidePanel() {
  const [tab, setTab] = useState<TabKey>("credit");

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="grid size-8 place-items-center rounded-ctl bg-acc/15 text-acc">
          <BookOpen size={18} weight="bold" />
        </div>
        <div>
          <h2 className="text-[15.5px] font-bold text-fg">Huong dan & Quy chuan Van hanh</h2>
          <p className="text-[11.5px] text-mut">
            Quy tinh credit, tao anh hang loat va dieu phoi trinh duyet CloakBrowser
          </p>
        </div>
      </div>

      {/* Inner Tabs */}
      <div className="flex gap-1 overflow-x-auto rounded-ctl border border-line2 bg-panel2 p-1 slim-scroll">
        {(
          [
            { key: "credit", label: "Credit & Che do Chay", icon: <Coins size={14} /> },
            { key: "batch", label: "Batch & Pool", icon: <Images size={14} /> },
            { key: "safety", label: "An toan", icon: <ShieldCheck size={14} /> },
            { key: "shortcuts", label: "Meo & Phim tat", icon: <Keyboard size={14} /> },
          ] as { key: TabKey; label: string; icon: React.ReactNode }[]
        ).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[12px] font-semibold transition-colors whitespace-nowrap ${
              tab === t.key
                ? "bg-acc/15 text-acc"
                : "text-dim hover:text-fg hover:bg-line/50"
            }`}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="space-y-4 text-[12.5px] leading-relaxed text-dim">
        {tab === "credit" && (
          <div className="space-y-4">
            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <Sparkle size={16} className="text-acc" weight="fill" />
                <span>Quy tac tru Credit cua Google Flow</span>
              </div>
              <ul className="space-y-2 list-disc list-inside text-dim">
                <li>
                  <strong className="text-fg">Tao anh thanh cong:</strong> Moi anh hoan thanh toan khoang <span className="font-semibold text-acc">~1 credit</span> tru truc tiep vao han muc goi cua tai khoan Google.
                </li>
                <li>
                  <strong className="text-fg">Bi tu choi (Rejected):</strong> Neu prompt kich hoat bo loc an toan cua Google, he thong ghi nhan ma phan hoi loi va <span className="font-semibold text-ok">hoan toan 0 credit</span> (khong bi tru).
                </li>
                <li>
                  <strong className="text-fg">That bai ky thuat:</strong> Neu request bi ngang mang hoac timeout truoc khi Google xu ly, credit se khong bi tru.
                </li>
              </ul>
            </div>

            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <Flask size={16} className="text-acc" />
                <span>Che do Thu nghiem (Dry-run)</span>
              </div>
              <p>
                Khi bam <strong className="text-fg">Dry-run</strong> hoac <strong className="text-fg">Batch dry-run</strong>:
              </p>
              <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                <li>He thong chay toan bo pipeline: xac thuc du an, kiem tra token phien, tai anh tham chieu i2i, mo phong hang doi Account Pool.</li>
                <li><strong className="text-acc">Luon tieu ton 0 credit</strong> vi request dung ngay truoc khi gui lenh tinh phi len may chu Google.</li>
                <li>Rat huu ich de kiem tra cu phap prompt, do on dinh cua profile truoc khi chay that.</li>
              </ul>
            </div>
          </div>
        )}

        {tab === "batch" && (
          <div className="space-y-4">
            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <Images size={16} className="text-acc" />
                <span>Cu phap & Quy chuan Batch Prompt</span>
              </div>
              <p>
                Trong che do Batch, ban co nhieu prompt cung mot luc:
              </p>
              <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                <li>Moi dong van ban tuong ung voi <strong className="text-fg">1 anh doc lap</strong>. Dong trong duoc tu dong bo qua.</li>
                <li>Ho tro toi da <strong className="text-fg">300 anh/batch</strong> trong mot luot chay.</li>
                <li>Moi dong co do dai toi da 2000 ky tu.</li>
              </ul>
            </div>

            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <Cpu size={16} className="text-acc" />
                <span>Cong thuc Phan bo Tai & Tiet kiem RAM</span>
              </div>
              <p>
                He thong phan bo tai khoan song song theo cong thuc:
              </p>
              <div className="my-2 rounded bg-panel px-3 py-2 font-mono text-[12px] text-acc border border-line2">
                N_alloc = min(N, M_RAM, ceil(J / Q_target))
              </div>
              <ul className="space-y-1.5 list-disc list-inside text-dim">
                <li><strong className="text-fg">J:</strong> Tong so anh trong batch.</li>
                <li><strong className="text-fg">Q_target:</strong> Nguong anh tren moi account (mac dinh 25 anh/account).</li>
                <li><strong className="text-fg">M_RAM:</strong> Gioi han so trinh duyet chay dong thoi (mac dinh 4) de chong qua tai RAM.</li>
                <li><strong className="text-fg">Co che Standby:</strong> Cac tai khoan chua den luot hoac ranh roi se luon duoc dong trinh duyet de giai phong 100% RAM. Khi can phan viec, he thong tu danh thuc (wake).</li>
              </ul>
            </div>

            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-1">
                <CheckCircle size={16} className="text-acc" />
                <span>Anh tham chieu Image-to-Image (i2i)</span>
              </div>
              <p className="mt-1">
                Dien duong dan tep anh cuc bo (vi du: <code className="font-mono text-acc">out/outputs/.../shot_001.jpg</code>). He thong se tu dong chuyen tat ca cac dong prompt trong batch sang che do tham chieu i2i, giup dien mao nhan vat va phong cach hinh anh xuyen suot.
              </p>
            </div>
          </div>
        )}

        {tab === "safety" && (
          <div className="space-y-4">
            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <Clock size={16} className="text-warn" />
                <span>Nguyen tac Khong can thiep Tab Trinh duyet</span>
              </div>
              <p>
                Khi mot tac vu (tao anh hoac batch) dang chay:
              </p>
              <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                <li>Playground ket noi va dieu khien truc tiep tab Flow trong <strong className="text-fg">CloakBrowser</strong> qua giao thuc CDP.</li>
                <li><strong className="text-warn">Khong click chuot, reload hoac chuyen huong tab Flow do</strong> bang tay trong luc bot dang thao tac de tranh xung dot session va lam hong request.</li>
                <li>Sau khi hoan thanh tao anh, ban co tu do mo xem hoac tai anh binh thuong.</li>
              </ul>
            </div>

            <div className="rounded-ctl border border-line2 bg-panel2 p-4">
              <div className="flex items-center gap-2 text-fg font-bold mb-2">
                <ShieldCheck size={16} className="text-ok" />
                <span>Bo ngan Mach Bao ve Tai khoan (Circuit Breaker)</span>
              </div>
              <p>
                Nham bao ve tai khoan khoi bi Google gan co spam hoac tam khoa:
              </p>
              <ul className="mt-2 space-y-1.5 list-disc list-inside text-dim">
                <li>Neu gap loi <strong className="text-fg">429 (Too Many Requests)</strong>: Tai khoan se tu dong kich hoat Cooldown va tam dung trong vai phut.</li>
                <li>Neu gap loi <strong className="text-fg">403 (Het phien/Auth expired)</strong>: He thong danh dau tai khoan can dang nhap lai vi gui lap lai gay nghi van.</li>
                <li>Ban co the mo tab <strong className="text-fg">Tai khoan</strong> bat ky luc nao de kiem tra chi tiet trang thai hoac reset cooldown.</li>
              </ul>
            </div>
          </div>
        )}

        {tab === "shortcuts" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
              <span>Chay tao anh nhanh khi dang nhap Prompt</span>
              <kbd className="rounded border border-line2 bg-panel px-2 py-1 font-mono text-[11px] text-fg">
                Ctrl + Enter
              </kbd>
            </div>
            <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
              <span>Chuyen doi giua cac tab</span>
              <kbd className="rounded border border-line2 bg-panel px-2 py-1 font-mono text-[11px] text-fg">
                Alt + 1-4
              </kbd>
            </div>
            <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 p-3">
              <span>Tai trang Thai thai (Status)</span>
              <kbd className="rounded border border-line2 bg-panel px-2 py-1 font-mono text-[11px] text-fg">
                R
              </kbd>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
