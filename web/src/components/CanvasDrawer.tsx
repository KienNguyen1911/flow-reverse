import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowsCounterClockwise,
  CheckCircle,
  Copy,
  DownloadSimple,
  FilmSlate,
  Image as ImageIcon,
  Info,
  ListDashes,
  Play,
  Sparkle,
  Terminal,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { Job, JobEvent } from "../types";
import { Spinner } from "./ui";

export interface CanvasDrawerNode {
  id: string;
  type: "ref" | "image" | "video" | "last_frame";
  x: number;
  y: number;
  label?: string | null;
  prompt: string;
  fileName?: string | null;
  aspectRatio: string;
  seed: number | null;
  sourceImageId: string | null;
  sourceImageIds?: string[];
  videoRatio: string;
  resolution: string;
  imageAspectRatio: string;
  autoImagePrompt: string;
  removeWatermark?: boolean;
  jobId: string | null;
  status: "idle" | "queued" | "running" | "succeeded" | "failed" | "rejected" | "skipped";
  fileUrl?: string | null;
  videoUrl?: string | null;
  frameUrl?: string | null;
  reason?: string | null;
  elapsedS?: number | null;
}

interface CanvasDrawerProps {
  node: CanvasDrawerNode | null;
  allNodes: CanvasDrawerNode[];
  onClose: () => void;
  onRunNode: (id: string, dry: boolean) => void;
  onRemoveNode: (id: string) => void;
  onUpdatePrompt?: (id: string, prompt: string) => void;
}

const KIND_CLS: Record<string, string> = {
  step: "text-dim border-line2 bg-panel2",
  info: "text-dim border-line2 bg-panel2",
  capture: "text-acc border-acc/30 bg-acc/10",
  fired: "text-acc border-acc/30 bg-acc/10",
  response: "text-acc border-acc/30 bg-acc/10",
  download: "text-ok border-ok/30 bg-ok/10",
  done: "text-ok border-ok/30 bg-ok/10",
  warn: "text-warn border-warn/30 bg-warn/10",
  retry: "text-warn border-warn/30 bg-warn/10",
  error: "text-err border-err/30 bg-err/10",
  debug: "text-mut border-line bg-panel2",
};

function hhmmss(ts: number) {
  return new Date(ts).toTimeString().slice(0, 8);
}

interface ErrorDiagnosis {
  code: string;
  title: string;
  explanation: string;
  fixHint: string;
}

function diagnoseError(reason: string | null | undefined): ErrorDiagnosis {
  const r = (reason || "").trim();
  const lower = r.toLowerCase();

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

  if (lower.includes("validation") || lower.includes("422") || lower.includes("invalid_argument")) {
    return {
      code: "VALIDATION_ERROR",
      title: "Tham số đầu vào không hợp lệ",
      explanation:
        "Dữ liệu gửi lên server không đúng định dạng hoặc vượt quá giới hạn cho phép (độ dài prompt, tỷ lệ khung hình, seed,...).",
      fixHint:
        "Kiểm tra lại độ dài prompt (tối đa 5.000 ký tự) và chọn tỷ lệ khung hình đã được xác thực.",
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

export function CanvasDrawer({ node, allNodes, onClose, onRunNode, onRemoveNode, onUpdatePrompt }: CanvasDrawerProps) {
  const [job, setJob] = useState<Job | null>(null);
  const [loadingJob, setLoadingJob] = useState(false);
  const [activeTab, setActiveTab] = useState<"error" | "logs" | "config" | "preview">("error");
  const [copiedError, setCopiedError] = useState(false);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const [aiGenerating, setAiGenerating] = useState(false);
  const [customHint, setCustomHint] = useState("");
  const [selectedSkill, setSelectedSkill] = useState("");
  const [skillsList, setSkillsList] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    api.agentSkills().then((res) => {
      if (res.skills) {
        setSkillsList(res.skills.map((s) => ({ id: s.id, name: s.name })));
      }
    }).catch(() => {});
  }, []);

  const handleDrawerGeneratePrompt = async () => {
    if (!node) return;
    setAiGenerating(true);
    try {
      const sids = node.type === "image" && node.sourceImageIds && node.sourceImageIds.length > 0
        ? node.sourceImageIds
        : node.sourceImageId ? [node.sourceImageId] : [];
      const urls: string[] = [];
      for (const sid of sids) {
        const p = allNodes.find((x) => x.id === sid);
        if (p?.fileUrl) urls.push(p.fileUrl);
        else if (p?.videoUrl) urls.push(p.videoUrl);
      }
      const isCont = node.type === "video" && !!node.sourceImageId &&
        (() => {
          const p = allNodes.find((x) => x.id === node.sourceImageId);
          return p?.type === "last_frame" || p?.type === "video";
        })();

      const res = await api.generateNodePrompt({
        node_id: node.id,
        node_type: node.type as "image" | "video",
        upstream_media_urls: urls,
        skill_id: selectedSkill || undefined,
        custom_hint: customHint.trim() || undefined,
        is_video_continuation: isCont,
      });

      if (res.ok && res.prompt) {
        onUpdatePrompt?.(node.id, res.prompt);
      }
    } catch (err: any) {
      alert(`Lỗi sinh prompt: ${err?.message || err}`);
    } finally {
      setAiGenerating(false);
    }
  };

  const hasError =
    node &&
    (node.status === "failed" || node.status === "rejected" || node.status === "skipped" || !!node.reason);

  // default tab on node change
  useEffect(() => {
    if (!node) return;
    if (hasError) {
      setActiveTab("error");
    } else if (node.fileUrl || node.videoUrl) {
      setActiveTab("preview");
    } else {
      setActiveTab("logs");
    }
    setJob(null);
  }, [node?.id, hasError]);

  // poll job events when open
  useEffect(() => {
    if (!node?.jobId) {
      setJob(null);
      return;
    }
    let stop = false;
    setLoadingJob(true);

    const fetchJob = async () => {
      try {
        const j = await api.job(node.jobId!);
        if (!stop) {
          setJob(j);
          setLoadingJob(false);
        }
      } catch {
        if (!stop) setLoadingJob(false);
      }
    };

    fetchJob();

    const isRunning = node.status === "running" || node.status === "queued";
    if (isRunning) {
      const t = window.setInterval(fetchJob, 1200);
      return () => {
        stop = true;
        window.clearInterval(t);
      };
    }
    return () => {
      stop = true;
    };
  }, [node?.jobId, node?.status]);

  // auto scroll logs
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (near) el.scrollTop = el.scrollHeight;
  }, [job?.events?.length]);

  const diagnosis = useMemo(() => {
    return diagnoseError(node?.reason || job?.error || (job?.result?.reason as string));
  }, [node?.reason, job?.error, job?.result]);

  const copyErrorText = () => {
    if (!node) return;
    const txt = `[${diagnosis.code}] ${diagnosis.title}\n\nLý do: ${node.reason || "Không rõ"}\n\nGiải thích: ${diagnosis.explanation}\n\nGợi ý khắc phục:\n${diagnosis.fixHint}`;
    navigator.clipboard.writeText(txt);
    setCopiedError(true);
    setTimeout(() => setCopiedError(false), 2000);
  };

  const copyAllLogs = () => {
    if (!job?.events || job.events.length === 0) return;
    const lines = job.events.map((e) => {
      const time = hhmmss(e.ts_ms);
      const dataStr = e.data && Object.keys(e.data).length > 0 ? ` ${JSON.stringify(e.data)}` : "";
      return `[${time}] [${e.kind}] ${e.message}${dataStr}`;
    });
    navigator.clipboard.writeText(lines.join("\n"));
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  if (!node) return null;

  const upstreamIds =
    Array.isArray(node.sourceImageIds) && node.sourceImageIds.length > 0
      ? node.sourceImageIds
      : node.sourceImageId
        ? [node.sourceImageId]
        : [];
  const upstreams = upstreamIds
    .map((id) => allNodes.find((x) => x.id === id))
    .filter(Boolean) as CanvasDrawerNode[];

  const nodeTitle =
    node.label ||
    (node.type === "ref"
      ? "Ảnh tham chiếu"
      : node.type === "image"
        ? "Node Ảnh"
        : node.type === "video"
          ? "Node Video"
          : "Trích xuất Frame Cuối");

  const nodeIcon =
    node.type === "ref" ? (
      <UploadSimple size={15} />
    ) : node.type === "image" ? (
      <ImageIcon size={15} />
    ) : node.type === "video" ? (
      <VideoCamera size={15} />
    ) : (
      <FilmSlate size={15} />
    );

  return (
    <div className="fixed inset-0 z-50 overflow-hidden pointer-events-none">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/45 backdrop-blur-[2px] pointer-events-auto transition-opacity"
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <aside className="absolute top-0 right-0 bottom-0 w-[480px] max-w-[92vw] bg-panel border-l border-line2 shadow-2xl flex flex-col pointer-events-auto animate-in slide-in-from-right duration-250 ease-out">
        {/* Header */}
        <header className="flex items-center justify-between px-4 sm:px-5 h-14 border-b border-line2 bg-panel2 shrink-0">
          <div className="flex items-center gap-2.5 truncate">
            <span
              className={`grid place-items-center size-7 rounded-ctl shrink-0 ${
                node.type === "ref" || node.type === "image"
                  ? "bg-acc/15 text-acc"
                  : node.type === "video"
                    ? "bg-ok/15 text-ok"
                    : "bg-purple-500/15 text-purple-400"
              }`}
            >
              {nodeIcon}
            </span>
            <div className="flex flex-col truncate">
              <span className="text-[13px] font-bold text-fg truncate">{nodeTitle}</span>
              <span className="text-[10px] font-mono text-mut truncate">{node.id}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {node.status === "running" ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-acc/40 bg-acc/10 text-acc text-[11px] font-semibold">
                <Spinner size={11} />
                Đang chạy
              </span>
            ) : node.status === "queued" ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-line2 bg-panel text-dim text-[11px] font-semibold">
                Trong hàng đợi
              </span>
            ) : node.status === "succeeded" ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-ok/40 bg-ok/10 text-ok text-[11px] font-semibold">
                <CheckCircle size={12} weight="fill" />
                Thành công
              </span>
            ) : hasError ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-err/40 bg-err/10 text-err text-[11px] font-semibold">
                <Warning size={12} weight="fill" />
                {node.status === "rejected" ? "Bị từ chối" : node.status === "skipped" ? "Bỏ qua" : "Thất bại"}
              </span>
            ) : null}

            <button
              onClick={onClose}
              className="grid place-items-center size-7 rounded-ctl hover:bg-panel border border-transparent hover:border-line2 text-mut hover:text-fg transition-colors cursor-pointer"
              title="Đóng (Esc)"
            >
              <X size={15} />
            </button>
          </div>
        </header>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 px-4 border-b border-line2 bg-panel shrink-0 text-[11.5px] font-semibold">
          {hasError && (
            <button
              onClick={() => setActiveTab("error")}
              className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
                activeTab === "error"
                  ? "border-err text-err font-bold"
                  : "border-transparent text-dim hover:text-fg"
              }`}
            >
              <Warning size={13} weight="fill" className="text-err" />
              <span>Lỗi & Giải pháp</span>
            </button>
          )}

          <button
            onClick={() => setActiveTab("logs")}
            className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === "logs"
                ? "border-acc text-acc font-bold"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <ListDashes size={13} />
            <span>Nhật ký (Logs)</span>
            {job?.events && job.events.length > 0 && (
              <span className="size-4 rounded-full bg-panel2 border border-line2 text-[9px] font-mono grid place-items-center text-mut">
                {job.events.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("config")}
            className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === "config"
                ? "border-acc text-acc font-bold"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            <Info size={13} />
            <span>Cấu hình</span>
          </button>

          {(node.fileUrl || node.videoUrl) && (
            <button
              onClick={() => setActiveTab("preview")}
              className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
                activeTab === "preview"
                  ? "border-ok text-ok font-bold"
                  : "border-transparent text-dim hover:text-fg"
              }`}
            >
              <CheckCircle size={13} weight="fill" className="text-ok" />
              <span>Kết quả</span>
            </button>
          )}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 slim-scroll flex flex-col gap-4 text-[12px]">
          {/* TAB: ERROR & SOLUTIONS */}
          {activeTab === "error" && (
            <div className="flex flex-col gap-3.5">
              {/* Error code & badge */}
              <div className="rounded-panel border border-err/35 bg-err/5 p-4 flex flex-col gap-2.5 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="grid place-items-center size-6 rounded-full bg-err/20 text-err">
                      <Warning size={14} weight="fill" />
                    </span>
                    <span className="font-bold text-[13px] text-err">{diagnosis.title}</span>
                  </div>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-err/15 text-err border border-err/25">
                    {diagnosis.code}
                  </span>
                </div>

                {/* Raw reason text */}
                <div className="rounded-ctl bg-ink/70 border border-err/20 p-2.5 font-mono text-[11px] leading-relaxed text-err break-all select-text">
                  {node.reason || job?.error || "Không có thông tin chi tiết lỗi."}
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={copyErrorText}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-ctl border border-err/30 bg-err/10 hover:bg-err/20 text-err text-[11px] font-semibold cursor-pointer transition-colors"
                  >
                    <Copy size={12} />
                    <span>{copiedError ? "Đã sao chép!" : "Sao chép thông báo lỗi"}</span>
                  </button>
                </div>
              </div>

              {/* Detailed Explanation */}
              <div className="rounded-panel border border-line2 bg-panel2 p-3.5 flex flex-col gap-1.5">
                <span className="text-[11px] font-bold text-fg uppercase tracking-wider">Nguyên nhân chi tiết</span>
                <p className="text-[12px] text-dim leading-relaxed">{diagnosis.explanation}</p>
              </div>

              {/* Actionable Fix Hint */}
              <div className="rounded-panel border border-acc/35 bg-acc/5 p-3.5 flex flex-col gap-2">
                <div className="flex items-center gap-1.5 text-acc font-bold text-[12px]">
                  <span>💡 Hướng dẫn khắc phục</span>
                </div>
                <div className="text-[12px] text-dim leading-relaxed whitespace-pre-line font-normal">
                  {diagnosis.fixHint}
                </div>
              </div>

              {/* Retry Button inside error view */}
              <div className="pt-2 flex items-center gap-2">
                <button
                  onClick={() => onRunNode(node.id, false)}
                  className="flex-1 h-9 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[12px] inline-flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
                >
                  <ArrowsCounterClockwise size={14} weight="bold" />
                  <span>Thử chạy lại ngay</span>
                </button>
                <button
                  onClick={() => onRunNode(node.id, true)}
                  className="h-9 px-3.5 rounded-ctl border border-line2 bg-panel2 hover:border-line hover:text-fg text-dim font-semibold text-[12px] cursor-pointer transition-colors"
                >
                  Dry-run
                </button>
              </div>
            </div>
          )}

          {/* TAB: LOGS */}
          {activeTab === "logs" && (
            <div className="flex flex-col gap-3 flex-1">
              {/* Job summary bar */}
              <div className="flex items-center justify-between text-[11px] text-mut pb-1">
                <div className="flex items-center gap-2 truncate">
                  <Terminal size={13} className="text-acc" />
                  <span className="font-mono text-dim truncate">{node.jobId ?? "Chưa có Job ID"}</span>
                </div>
                {job?.events && job.events.length > 0 && (
                  <button
                    onClick={copyAllLogs}
                    className="inline-flex items-center gap-1 text-[11px] text-dim hover:text-fg cursor-pointer transition-colors"
                  >
                    <Copy size={12} />
                    <span>{copiedLogs ? "Đã chép!" : "Sao chép log"}</span>
                  </button>
                )}
              </div>

              {/* Logs terminal box */}
              <div
                ref={scrollRef}
                className="flex-1 min-h-[300px] max-h-[500px] overflow-y-auto rounded-ctl border border-line2 bg-ink p-3 font-mono text-[11px] leading-relaxed select-text slim-scroll flex flex-col gap-1.5"
              >
                {loadingJob && !job ? (
                  <div className="grid place-items-center h-32 text-mut">
                    <Spinner size={16} />
                    <span className="text-[11px] mt-2">Đang tải nhật ký...</span>
                  </div>
                ) : !job || !job.events || job.events.length === 0 ? (
                  <div className="grid place-items-center h-32 text-mut text-center">
                    <p className="text-[11.5px]">Chưa có sự kiện thực thi nào.</p>
                    <p className="text-[10px] mt-1">Bấm "Chạy node" để bắt đầu ghi nhật ký.</p>
                  </div>
                ) : (
                  job.events.map((e: JobEvent, idx: number) => {
                    const cls = KIND_CLS[e.kind] || "text-dim border-line bg-panel2";
                    return (
                      <div key={idx} className="flex items-start gap-2 hover:bg-panel2/30 px-1 py-0.5 rounded">
                        <span className="text-mut text-[10px] shrink-0 pt-0.5">{hhmmss(e.ts_ms)}</span>
                        <span
                          className={`px-1.5 py-0.2 rounded border text-[9.5px] uppercase font-bold shrink-0 ${cls}`}
                        >
                          {e.kind}
                        </span>
                        <span className="text-fg/90 flex-1 break-words">{e.message}</span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* TAB: CONFIG */}
          {activeTab === "config" && (
            <div className="flex flex-col gap-3">
              {(node.type === "image" || node.type === "video") && (
                <div className="rounded-ctl border border-acc/35 bg-acc/5 p-3 flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                      <Sparkle size={13} weight="fill" className="text-acc" />
                      <span>AI Prompter Director</span>
                    </span>
                    <button
                      type="button"
                      disabled={aiGenerating}
                      onClick={handleDrawerGeneratePrompt}
                      className="inline-flex items-center gap-1 px-2.5 h-6 rounded-ctl bg-acc text-accink text-[10.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40"
                    >
                      {aiGenerating ? <Spinner size={10} /> : <Sparkle size={10} weight="fill" />}
                      <span>{aiGenerating ? "Đang sinh…" : "Tạo lại Prompt"}</span>
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-2">
                    {skillsList.length > 0 && (
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] text-mut font-semibold">Chọn Skill quy chuẩn:</label>
                        <select
                          value={selectedSkill}
                          onChange={(e) => setSelectedSkill(e.target.value)}
                          className="h-7 rounded-ctl border border-line2 bg-panel px-2 text-[11px] text-fg outline-none focus:border-acc"
                        >
                          <option value="">Tự động chọn theo loại node</option>
                          {skillsList.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-mut font-semibold">Ghi chú phong cách bổ sung (tùy chọn):</label>
                      <input
                        type="text"
                        value={customHint}
                        onChange={(e) => setCustomHint(e.target.value)}
                        placeholder="Ví dụ: Áo len cổ lọ màu be, phong cách tối giản studio..."
                        className="h-7 rounded-ctl border border-line2 bg-panel px-2 text-[11px] text-fg outline-none focus:border-acc"
                      />
                    </div>
                  </div>
                </div>
              )}

              {node.prompt && (
                <div className="flex flex-col gap-1">
                  <span className="text-[11px] font-semibold text-mut">Prompt</span>
                  <div className="rounded-ctl border border-line2 bg-panel2 p-3 text-[11.5px] font-mono text-fg leading-relaxed select-text break-words max-h-48 overflow-y-auto slim-scroll">
                    {node.prompt}
                  </div>
                </div>
              )}

              {node.type === "image" && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                    <span className="text-[10px] text-mut block">Tỷ lệ khung hình</span>
                    <span className="text-[12px] font-semibold text-fg">{node.aspectRatio}</span>
                  </div>
                  <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                    <span className="text-[10px] text-mut block">Seed</span>
                    <span className="text-[12px] font-mono text-fg">{node.seed ?? "Ngẫu nhiên"}</span>
                  </div>
                </div>
              )}

              {node.type === "video" && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                    <span className="text-[10px] text-mut block">Tỷ lệ video</span>
                    <span className="text-[12px] font-semibold text-fg">{node.videoRatio}</span>
                  </div>
                  <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                    <span className="text-[10px] text-mut block">Độ phân giải</span>
                    <span className="text-[12px] font-semibold text-fg">{node.resolution}</span>
                  </div>
                </div>
              )}

              {node.type === "last_frame" && (
                <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                  <span className="text-[10px] text-mut block">Xóa Watermark Flow</span>
                  <span className="text-[12px] font-semibold text-fg">
                    {node.removeWatermark ?? true ? "Bật (tự động xóa bằng OpenCV/Inpaint)" : "Tắt"}
                  </span>
                </div>
              )}

              {upstreams.length > 0 && (
                <div className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1.5">
                  <span className="text-[10px] text-mut">
                    {upstreams.length > 1
                      ? `Nguồn kết nối (${upstreams.length} ảnh tham chiếu)`
                      : "Nguồn kết nối (Upstream Node)"}
                  </span>
                  {upstreams.map((up) => (
                    <div key={up.id} className="flex items-center justify-between text-[11.5px] font-semibold text-fg">
                      <span className="truncate pr-2">
                        {up.type === "ref"
                          ? `Ảnh tham chiếu: ${up.fileName ?? up.id}`
                          : up.type === "video"
                            ? `Video: ${up.prompt.slice(0, 30)}...`
                            : up.type === "last_frame"
                              ? `Frame Cuối: ${up.id}`
                              : `Ảnh: ${up.prompt.slice(0, 30)}...`}
                      </span>
                      {up.fileUrl && (
                        <img
                          src={up.fileUrl}
                          alt=""
                          className="size-6 object-cover rounded border border-line2 shrink-0"
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {node.elapsedS != null && (
                <div className="rounded-ctl border border-line2 bg-panel2 p-2.5">
                  <span className="text-[10px] text-mut block">Thời gian thực thi</span>
                  <span className="text-[12px] font-mono text-fg">{node.elapsedS.toFixed(1)}s</span>
                </div>
              )}
            </div>
          )}

          {/* TAB: PREVIEW */}
          {activeTab === "preview" && (
            <div className="flex flex-col gap-3">
              {node.type === "video" && node.videoUrl ? (
                <div className="rounded-panel border border-line2 bg-panel2 overflow-hidden">
                  <video src={node.videoUrl} controls autoPlay loop className="w-full max-h-[360px]" />
                  <div className="p-3 flex items-center justify-between border-t border-line2">
                    <span className="text-[11px] font-mono text-mut truncate">{node.videoUrl}</span>
                    <a
                      href={node.videoUrl}
                      download
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[11px] cursor-pointer"
                    >
                      <DownloadSimple size={13} />
                      <span>Tải video</span>
                    </a>
                  </div>
                </div>
              ) : node.fileUrl ? (
                <div className="rounded-panel border border-line2 bg-panel2 overflow-hidden">
                  <img
                    src={node.fileUrl}
                    alt="Kết quả"
                    className="w-full max-h-[360px] object-contain bg-black/20"
                  />
                  <div className="p-3 flex items-center justify-between border-t border-line2">
                    <span className="text-[11px] font-mono text-mut truncate">{node.fileUrl}</span>
                    <a
                      href={node.fileUrl}
                      download
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[11px] cursor-pointer"
                    >
                      <DownloadSimple size={13} />
                      <span>Tải ảnh</span>
                    </a>
                  </div>
                </div>
              ) : (
                <div className="grid place-items-center h-32 text-mut text-center">
                  <span className="text-[11.5px]">Chưa có kết quả để hiển thị.</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <footer className="p-4 border-t border-line2 bg-panel2 shrink-0 flex items-center justify-between gap-2">
          <button
            onClick={() => onRemoveNode(node.id)}
            className="inline-flex items-center gap-1 px-3 h-8 rounded-ctl text-err hover:bg-err/10 border border-transparent hover:border-err/20 text-[11.5px] font-semibold cursor-pointer transition-colors"
          >
            <Trash size={13} />
            <span>Xóa node</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onRunNode(node.id, false)}
              className="inline-flex items-center gap-1.5 px-4 h-8 rounded-ctl bg-acc hover:bg-acc2 text-accink text-[12px] font-bold cursor-pointer transition-colors shadow-sm"
            >
              <Play size={11} weight="fill" />
              <span>Chạy lại</span>
            </button>
            <button
              onClick={onClose}
              className="px-3.5 h-8 rounded-ctl border border-line2 hover:border-line bg-panel text-dim hover:text-fg text-[12px] font-semibold cursor-pointer transition-colors"
            >
              Đóng
            </button>
          </div>
        </footer>
      </aside>
    </div>
  );
}
