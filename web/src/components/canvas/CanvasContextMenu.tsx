import { useEffect, useRef, type ReactNode } from "react";
import {
  FilmSlate,
  FlowArrow,
  Image as ImageIcon,
  Plus,
  UploadSimple,
  VideoCamera,
} from "@phosphor-icons/react";
import type { CanvasGroup, ContextMenuState, NodeType } from "./types";

const ITEM_CLS =
  "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer";

function MenuItem({
  icon,
  iconCls,
  label,
  onClick,
  disabled,
}: {
  icon: ReactNode;
  iconCls: string;
  label: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onPointerDown={(e) => e.stopPropagation()}
      onClick={onClick}
      disabled={disabled}
      className={
        disabled === undefined ? ITEM_CLS : `${ITEM_CLS} disabled:opacity-40 disabled:pointer-events-none`
      }
    >
      <span className={`grid place-items-center size-5 rounded-[4px] ${iconCls}`}>{icon}</span>
      <span>{label}</span>
    </button>
  );
}

/** Floating Context Menu (Right-Click on Canvas): add a node here, or group the selection. */
export function CanvasContextMenu({
  menu,
  groups,
  selectedCount,
  onAddNode,
  onCreateGroup,
  onAddToGroup,
  onClose,
}: {
  menu: ContextMenuState;
  groups: CanvasGroup[];
  selectedCount: number;
  onAddNode: (type: NodeType, canvasX: number, canvasY: number) => void;
  onCreateGroup: () => void;
  onAddToGroup: (groupId: string) => void;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on any pointer-down outside the menu.
  useEffect(() => {
    const handlePointerDown = (e: PointerEvent) => {
      if (menuRef.current && menuRef.current.contains(e.target as Node)) {
        return;
      }
      onClose();
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [menu, onClose]);

  return (
    <div
      ref={menuRef}
      className="fixed z-50 min-w-[210px] rounded-ctl border border-line2 bg-panel/95 backdrop-blur-md p-1.5 shadow-2xl animate-in fade-in zoom-in-95 duration-100 select-none text-[12.5px]"
      style={{
        left: Math.min(menu.x, window.innerWidth - 225),
        top: Math.min(menu.y, window.innerHeight - 210),
      }}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="px-2.5 py-1 text-[10px] font-bold text-mut uppercase tracking-wider border-b border-line mb-1">
        Thêm Node Mới
      </div>
      <MenuItem
        icon={<UploadSimple size={13} />}
        iconCls="bg-acc/15 text-acc"
        label="Ảnh tham chiếu"
        onClick={() => onAddNode("ref", menu.canvasX, menu.canvasY)}
      />
      <MenuItem
        icon={<ImageIcon size={13} />}
        iconCls="bg-acc/15 text-acc"
        label="Node Ảnh"
        onClick={() => onAddNode("image", menu.canvasX, menu.canvasY)}
      />
      <MenuItem
        icon={<VideoCamera size={13} />}
        iconCls="bg-ok/15 text-ok"
        label="Node Video"
        onClick={() => onAddNode("video", menu.canvasX, menu.canvasY)}
      />
      <MenuItem
        icon={<FilmSlate size={13} />}
        iconCls="bg-purple-500/15 text-purple-400"
        label="Frame Cuối"
        onClick={() => onAddNode("last_frame", menu.canvasX, menu.canvasY)}
      />

      <div className="px-2.5 py-1 mt-1 mb-1 text-[10px] font-bold text-mut uppercase tracking-wider border-t border-line pt-1.5">
        Nhóm
      </div>
      <MenuItem
        icon={<Plus size={13} />}
        iconCls="bg-acc/15 text-acc"
        label="Tạo nhóm từ node đã chọn"
        onClick={() => {
          onCreateGroup();
          onClose();
        }}
        disabled={selectedCount === 0}
      />
      {groups.length > 0 && (
        <MenuItem
          icon={<FlowArrow size={13} />}
          iconCls="bg-ok/15 text-ok"
          label={`Thêm vào ${groups[0].name}`}
          onClick={() => {
            if (groups[0]) {
              onAddToGroup(groups[0].id);
              onClose();
            }
          }}
          disabled={selectedCount === 0}
        />
      )}
    </div>
  );
}
