import { useEffect, useState } from "react";
import { useLimits, useNodeOptions } from "../hooks";
import { ConfigTab } from "./canvas-drawer/ConfigTab";
import { DrawerFooter, DrawerHeader, DrawerTabs } from "./canvas-drawer/DrawerChrome";
import { ErrorTab } from "./canvas-drawer/ErrorTab";
import { LogsTab } from "./canvas-drawer/LogsTab";
import { PreviewTab } from "./canvas-drawer/PreviewTab";
import type { CanvasDrawerNode, DrawerSection, DrawerTab } from "./canvas-drawer/types";
import { useAiPrompter } from "./canvas-drawer/useAiPrompter";
import { useDrawerJob } from "./canvas-drawer/useDrawerJob";

export type { CanvasDrawerNode } from "./canvas-drawer/types";

interface CanvasDrawerProps {
  node: CanvasDrawerNode | null;
  allNodes: CanvasDrawerNode[];
  /** Tab / vùng cần focus khi mở từ node body (pill, chip, nút Expand). */
  initialSection?: DrawerSection;
  onClose: () => void;
  onRunNode: (id: string, dry: boolean) => void;
  onRemoveNode: (id: string) => void;
  onUpdatePrompt?: (id: string, prompt: string) => void;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

export function CanvasDrawer({
  node,
  allNodes,
  initialSection = "config",
  onClose,
  onRunNode,
  onRemoveNode,
  onUpdatePrompt,
  onUpdateNode,
}: CanvasDrawerProps) {
  const limits = useLimits();
  // Danh sách option thật do backend trả về (nguồn: flow_catalog — bằng chứng capture).
  const opts = useNodeOptions();
  const [activeTab, setActiveTab] = useState<DrawerTab>("error");
  const { job, loadingJob, clearJob, logScrollRef, stopping, stopRetry } = useDrawerJob(node);
  const ai = useAiPrompter({ node, allNodes, onUpdatePrompt });

  const hasError =
    node &&
    (node.status === "failed" || node.status === "rejected" || node.status === "skipped" || !!node.reason);

  // default tab on node change
  useEffect(() => {
    if (!node) return;
    if (initialSection === "preview" && (node.fileUrl || node.videoUrl)) {
      setActiveTab("preview");
    } else if (initialSection === "logs") {
      setActiveTab("logs");
    } else if (initialSection === "error" && hasError) {
      setActiveTab("error");
    } else if (
      initialSection === "config" ||
      initialSection === "prompt" ||
      initialSection === "sources"
    ) {
      setActiveTab("config");
    } else if (hasError) {
      setActiveTab("error");
    } else if (node.fileUrl || node.videoUrl) {
      setActiveTab("preview");
    } else {
      setActiveTab("logs");
    }
    clearJob();
    // `initialSection` chỉ định tab lúc mở; đổi tab sau đó là quyền của người dùng.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node?.id, hasError]);

  const isRunning = node?.status === "running" || node?.status === "queued";

  if (!node) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden pointer-events-none">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/45 backdrop-blur-[2px] pointer-events-auto transition-opacity"
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <aside className="absolute top-0 right-0 bottom-0 w-[480px] max-w-[92vw] bg-panel border-l border-line2 shadow-2xl flex flex-col pointer-events-auto animate-in slide-in-from-right duration-250 ease-out">
        <DrawerHeader node={node} hasError={!!hasError} onClose={onClose} />

        <DrawerTabs node={node} job={job} hasError={!!hasError} activeTab={activeTab} onTabChange={setActiveTab} />

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 slim-scroll flex flex-col gap-4 text-[12px]">
          {activeTab === "error" && (
            <ErrorTab node={node} job={job} maxPromptChars={limits.max_prompt_chars} onRunNode={onRunNode} />
          )}

          {activeTab === "logs" && (
            <LogsTab
              node={node}
              job={job}
              loadingJob={loadingJob}
              isRunning={isRunning}
              stopping={stopping}
              onStopRetry={stopRetry}
              scrollRef={logScrollRef}
            />
          )}

          {activeTab === "config" && (
            <ConfigTab
              node={node}
              allNodes={allNodes}
              opts={opts}
              maxPromptChars={limits.max_prompt_chars}
              initialSection={initialSection}
              ai={ai}
              onShowPreview={() => setActiveTab("preview")}
              onUpdatePrompt={onUpdatePrompt}
              onUpdateNode={onUpdateNode}
            />
          )}

          {activeTab === "preview" && <PreviewTab node={node} />}
        </div>

        <DrawerFooter
          node={node}
          isRunning={isRunning}
          stopping={stopping}
          onStopRetry={stopRetry}
          onRunNode={onRunNode}
          onRemoveNode={onRemoveNode}
          onClose={onClose}
        />
      </aside>
    </div>
  );
}
