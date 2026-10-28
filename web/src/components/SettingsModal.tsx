import { useEffect, useState } from "react";
import { BookOpen, Code, Cpu, Gear, Images, Users, X } from "@phosphor-icons/react";
import type { PoolInfo, RunItem } from "../types";
import { AccountPanel } from "./AccountPanel";
import { AgentSettingsPanel } from "./AgentSettingsPanel";
import { ApiDocsPanel } from "./ApiDocsPanel";
import { Gallery } from "./Gallery";
import { GuidePanel } from "./GuidePanel";

export type SettingsTab = "gallery" | "accounts" | "agent" | "guide" | "docs";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  initialTab?: SettingsTab;
  runs: RunItem[];
  galleryLoading?: boolean;
  galleryError?: string | null;
  onRefreshGallery: () => void;
  pool: PoolInfo | null;
  onRefreshPool: () => void;
}

export function SettingsModal({
  open,
  onClose,
  initialTab = "gallery",
  runs,
  galleryLoading,
  galleryError,
  onRefreshGallery,
  pool,
  onRefreshPool,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);

  // Sync initial tab when modal opens
  useEffect(() => {
    if (open) {
      setActiveTab(initialTab);
    }
  }, [open, initialTab]);

  // Handle ESC key to close
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const activeCount = pool?.working_set.length ?? 0;

  const tabs: {
    key: SettingsTab;
    label: string;
    desc: string;
    icon: React.ReactNode;
    badge?: React.ReactNode;
  }[] = [
    {
      key: "gallery",
      label: "Thư viện",
      desc: "Lịch sử ảnh & video",
      icon: <Images size={17} />,
      badge: runs.length > 0 ? (
        <span className="font-mono text-[10px] text-mut">{runs.length}</span>
      ) : undefined,
    },
    {
      key: "accounts",
      label: "Tài khoản",
      desc: "Quản lý Browser Pool",
      icon: <Users size={17} />,
      badge: activeCount > 0 ? (
        <span className="size-4 grid place-items-center rounded-full bg-acc text-accink font-mono text-[9px] font-bold">
          {activeCount}
        </span>
      ) : pool ? (
        <span className="font-mono text-[10px] text-mut">{pool.n_total}</span>
      ) : undefined,
    },
    {
      key: "agent",
      label: "AI Agent",
      desc: "Local agy & pi CLI",
      icon: <Cpu size={17} />,
    },
    {
      key: "guide",
      label: "Hướng dẫn",
      desc: "Thao tác & phím tắt",
      icon: <BookOpen size={17} />,
    },
    {
      key: "docs",
      label: "Docs API",
      desc: "Đặc tả các endpoint",
      icon: <Code size={17} />,
    },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200 select-none"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="w-[80vw] h-[80vh] flex flex-col rounded-panel border border-line2 bg-panel shadow-2xl overflow-hidden relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-line bg-panel2 shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="grid place-items-center size-7 rounded-ctl bg-acc/15 text-acc">
              <Gear size={17} weight="fill" />
            </span>
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-bold text-fg">Cài đặt & Tiện ích</h2>
              <span className="text-[12px] text-mut font-medium">/</span>
              <span className="text-[13px] text-acc font-semibold">
                {tabs.find((t) => t.key === activeTab)?.label}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="inline-grid place-items-center size-8 rounded-ctl text-mut hover:text-fg hover:bg-line transition-colors cursor-pointer"
            title="Đóng (Esc)"
            aria-label="Đóng"
          >
            <X size={18} weight="bold" />
          </button>
        </div>

        {/* 2-Column Body: Left Sidebar + Right Content */}
        <div className="flex-1 min-h-0 flex overflow-hidden">
          {/* Left Sidebar (230px) */}
          <div className="w-[230px] shrink-0 border-r border-line bg-panel2/70 p-3 flex flex-col justify-between overflow-y-auto slim-scroll">
            <div className="flex flex-col gap-1.5">
              <div className="px-2.5 py-1 text-[10px] font-bold text-mut uppercase tracking-wider">
                Menu Tiện ích
              </div>
              {tabs.map((t) => {
                const isActive = activeTab === t.key;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setActiveTab(t.key)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-ctl text-left transition-colors cursor-pointer ${
                      isActive
                        ? "bg-acc/15 text-acc font-semibold shadow-sm shadow-acc/10"
                        : "text-dim hover:text-fg hover:bg-panel2"
                    }`}
                  >
                    <span
                      className={`grid place-items-center size-6 rounded-[6px] shrink-0 ${
                        isActive ? "text-acc" : "text-mut"
                      }`}
                    >
                      {t.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-[12.5px] leading-tight truncate font-medium">
                          {t.label}
                        </span>
                        {t.badge}
                      </div>
                      <p className="text-[10px] text-mut leading-tight truncate mt-0.5">
                        {t.desc}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Sidebar Footer */}
            <div className="pt-3 border-t border-line/60 px-2 text-[10.5px] text-mut flex items-center justify-between">
              <span>Flow Bench</span>
              <span className="font-mono text-[9.5px]">v0.2</span>
            </div>
          </div>

          {/* Right Main Content Area */}
          <div className="flex-1 min-w-0 h-full overflow-y-auto slim-scroll p-4 sm:p-6 bg-ink/30">
            {activeTab === "gallery" && (
              <Gallery
                runs={runs}
                loading={galleryLoading}
                error={galleryError}
                onRefresh={() => void onRefreshGallery()}
              />
            )}

            {activeTab === "accounts" && (
              <AccountPanel
                pool={pool}
                onRefreshPool={() => {
                  onRefreshPool();
                }}
              />
            )}

            {activeTab === "agent" && <AgentSettingsPanel />}

            {activeTab === "guide" && <GuidePanel />}

            {activeTab === "docs" && <ApiDocsPanel />}
          </div>
        </div>
      </div>
    </div>
  );
}
