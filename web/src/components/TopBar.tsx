import { ArrowClockwise } from "@phosphor-icons/react";
import type { Status } from "../types";
import { Chip, IconBtn } from "./ui";

export function TopBar({ status, onRefresh }: { status: Status | null; onRefresh: () => void }) {
  const cdpOk = !!status?.cdp_ok;
  const hasTab = !!status?.flow_tab_url;
  const projectShort = status?.flow_project_id ? status.flow_project_id.slice(0, 8) : null;
  const cooldown = status?.breaker?.cooldown_remaining_s ?? 0;
  const accepted = status?.breaker?.total_accepted ?? 0;

  // "Chrome/146.0.7680.177" -> "Chrome 146"
  const browserShort = (() => {
    const raw = status?.browser;
    if (!raw) return null;
    const [name, ver] = raw.split("/");
    const major = (ver || "").split(".")[0];
    return major ? `${name} ${major}` : name;
  })();

  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <div className="flex items-center gap-2.5">
        <div className="grid size-6 place-items-center rounded-[7px] bg-acc">
          <span className="block size-2.5 rounded-[3px] bg-accink" />
        </div>
        <div className="leading-none">
          <h1 className="text-[16px] font-bold tracking-tight">Flow Bench</h1>
          <p className="mt-0.5 text-[11.5px] font-medium text-mut">Playground tạo ảnh Google Flow</p>
        </div>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Chip tone={cdpOk ? "ok" : "err"} live={false} title={status?.error ?? status?.cdp_url}>
          {cdpOk ? `Browser ${browserShort ?? "OK"}` : "Browser offline"}
        </Chip>

        <Chip
          tone={hasTab ? "ok" : cdpOk ? "warn" : "neutral"}
          title={status?.flow_tab_url ?? "Mở flow.google.com trong CloakBrowser"}
        >
          {hasTab ? (
            <>
              Tab Flow
              {projectShort ? (
                <span className="hidden sm:inline font-mono text-[10.5px] text-mut">
                  {projectShort}
                </span>
              ) : null}
            </>
          ) : (
            "Chưa thấy tab Flow"
          )}
        </Chip>

        {accepted > 0 ? (
          <Chip tone="neutral" title="Số ảnh đã được Google nhận (≈ số credit đã dùng, do client này đếm)">
            Đã nhận {accepted} ảnh
          </Chip>
        ) : null}

        {cooldown > 0 ? (
          <Chip tone="warn" live title={status?.breaker?.cooldown_reason ?? ""}>
            Tạm dừng {Math.ceil(cooldown / 60)} phút
          </Chip>
        ) : null}

        <IconBtn label="Cập nhật trạng thái" onClick={onRefresh}>
          <ArrowClockwise size={15} />
        </IconBtn>
      </div>
    </header>
  );
}
