import { useEffect, useState } from "react";
import {
  ArrowClockwise,
  CheckCircle,
  Play,
  Plus,
  Power,
  Sliders,
  Stop,
  Trash,
  Users,
  Warning,
  XCircle,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { AccountDetail, PoolAccount, PoolInfo } from "../types";
import { Btn, Chip, Spinner } from "./ui";

interface Props {
  pool: PoolInfo | null;
  onRefreshPool: () => void;
}

export function AccountPanel({ pool, onRefreshPool }: Props) {
  const [newId, setNewId] = useState("");
  const [newPort, setNewPort] = useState<number | "">("");
  const [newNote, setNewNote] = useState("");
  const [createProfile, setCreateProfile] = useState(true);
  const [addBusy, setAddBusy] = useState(false);
  const [addMsg, setAddMsg] = useState<{ type: "ok" | "err"; text: string; newAccId?: string } | null>(null);

  const [targetJobs, setTargetJobs] = useState<number>(25);
  const [maxRam, setMaxRam] = useState<number>(4);
  const [saveConfigBusy, setSaveConfigBusy] = useState(false);
  const [configMsg, setConfigMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [busyAcc, setBusyAcc] = useState<Record<string, string>>({});
  const [probedDetails, setProbedDetails] = useState<Record<string, AccountDetail["flow"]>>({});
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; deleteVault: boolean } | null>(null);

  useEffect(() => {
    void loadNextPort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (pool) {
      setTargetJobs(pool.target_jobs_per_account || 25);
      setMaxRam(pool.max_active_browsers || 4);
    }
  }, [pool]);

  const loadNextPort = async () => {
    try {
      const res = await api.nextPoolPort();
      if (res?.next_port) {
        setNewPort(res.next_port);
      }
    } catch {
      // ignore
    }
  };

  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newId.trim()) return;
    setAddBusy(true);
    setAddMsg(null);
    try {
      const res = await api.addPoolAccount({
        id: newId.trim(),
        cdp_port: newPort ? Number(newPort) : undefined,
        note: newNote.trim(),
        create_profile: createProfile,
        enabled: true,
      });
      setAddMsg({
        type: "ok",
        text: `Đã tạo account "${res.account.id}" tren cong :${res.account.cdp_port}!`,
        newAccId: res.account.id,
      });
      setNewId("");
      setNewNote("");
      void loadNextPort();
      onRefreshPool();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setAddMsg({ type: "err", text: msg });
    } finally {
      setAddBusy(false);
    }
  };

  const handleWake = async (aid: string) => {
    setBusyAcc((b) => ({ ...b, [aid]: "wake" }));
    try {
      await api.poolAccount(aid, "wake");
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Khong mo duoc trinh duyet: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[aid];
        return next;
      });
    }
  };

  const handleHibernate = async (aid: string) => {
    setBusyAcc((b) => ({ ...b, [aid]: "hibernate" }));
    try {
      await api.poolAccount(aid, "hibernate");
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Khong dong duoc trinh duyet: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[aid];
        return next;
      });
    }
  };

  const handleProbe = async (aid: string) => {
    setBusyAcc((b) => ({ ...b, [aid]: "probe" }));
    try {
      const detail = await api.poolAccountDetail(aid);
      setProbedDetails((prev) => ({ ...prev, [aid]: detail.flow }));
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Loi kiem tra session: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[aid];
        return next;
      });
    }
  };

  const handleToggleEnabled = async (acc: PoolAccount) => {
    setBusyAcc((b) => ({ ...b, [acc.id]: "toggle" }));
    try {
      await api.updatePoolAccount(acc.id, { enabled: !acc.enabled });
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Loi cap nhat: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[acc.id];
        return next;
      });
    }
  };

  const handleResetCooldown = async (aid: string) => {
    setBusyAcc((b) => ({ ...b, [aid]: "reset" }));
    try {
      await api.poolAccount(aid, "reset");
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Loi reset cooldown: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[aid];
        return next;
      });
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteConfirm) return;
    const { id, deleteVault } = deleteConfirm;
    setBusyAcc((b) => ({ ...b, [id]: "delete" }));
    try {
      await api.removePoolAccount(id, deleteVault);
      setDeleteConfirm(null);
      onRefreshPool();
    } catch (err: unknown) {
      alert(`Khong xoa duoc account: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusyAcc((b) => {
        const next = { ...b };
        delete next[id];
        return next;
      });
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveConfigBusy(true);
    setConfigMsg(null);
    try {
      await api.poolConfig({
        target_jobs_per_account: Number(targetJobs),
        max_active_browsers: Number(maxRam),
      });
      setConfigMsg({ type: "ok", text: "Da luu cai dat Pool thanh cong!" });
      onRefreshPool();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setConfigMsg({ type: "err", text: msg });
    } finally {
      setSaveConfigBusy(false);
    }
  };

  const accounts = pool?.accounts ?? [];
  const runningCount = accounts.filter((a) => a.running).length;
  const standbyCount = Math.max(0, accounts.length - runningCount);
  const coolingCount = accounts.filter((a) => a.cooldown_remaining_s > 0).length;

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-5">
      {/* Quick Metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-ctl border border-line2 bg-panel2 p-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-mut">Tong Account (N)</span>
          <p className="mt-1 text-[20px] font-bold text-fg">{pool?.n_total ?? 0}</p>
        </div>
        <div className="rounded-ctl border border-line2 bg-panel2 p-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ok">Dang Mo</span>
          <p className="mt-1 text-[20px] font-bold text-ok">{runningCount}</p>
        </div>
        <div className="rounded-ctl border border-line2 bg-panel2 p-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-dim">Standby</span>
          <p className="mt-1 text-[20px] font-bold text-dim">{standbyCount}</p>
        </div>
        <div className="rounded-ctl border border-line2 bg-panel2 p-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-warn">Cooldown</span>
          <p className="mt-1 text-[20px] font-bold text-warn">{coolingCount}</p>
        </div>
      </div>

      {/* Add Account */}
      <div className="rounded-panel border border-line2 bg-panel2 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Plus size={16} className="text-acc" weight="bold" />
          <h3 className="text-[13.5px] font-bold text-fg">Them Account / Browser Profile Moi</h3>
        </div>

        <form onSubmit={handleAddAccount} className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[11.5px] font-semibold text-dim">
                Account ID <span className="text-acc">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="vi du: acc_02"
                pattern="^[A-Za-z0-9][A-Za-z0-9._-]*$"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12.5px] text-fg focus:border-acc/70 focus:outline-none font-mono"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] font-semibold text-dim">
                Cong CDP Port <span className="text-acc">*</span>
              </label>
              <input
                type="number"
                required
                min={1024}
                max={65535}
                value={newPort}
                onChange={(e) => setNewPort(Number(e.target.value) || "")}
                className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12.5px] text-fg focus:border-acc/70 focus:outline-none font-mono"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11.5px] font-semibold text-dim">Ghi chu (Tuy chon)</label>
              <input
                type="text"
                placeholder="vi du: Acc du phong"
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12.5px] text-fg focus:border-acc/70 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <label className="flex items-center gap-2 text-[12px] text-dim cursor-pointer select-none">
              <input
                type="checkbox"
                checked={createProfile}
                onChange={(e) => setCreateProfile(e.target.checked)}
                className="size-4 rounded accent-acc"
              />
              <span>Tu dong tao thu muc profile trong <code>browser_vault/</code> (sinh seed ngau nhien 8 so)</span>
            </label>

            <Btn variant="primary" type="submit" busy={addBusy} className="h-8 text-[12.5px]">
              + Tao Account
            </Btn>
          </div>
        </form>

        {addMsg && (
          <div
            className={`mt-3 flex items-center justify-between rounded-ctl border px-3 py-2 text-[12px] ${
              addMsg.type === "ok"
                ? "border-ok/30 bg-ok/10 text-ok"
                : "border-err/30 bg-err/10 text-err"
            }`}
          >
            <div className="flex items-center gap-2">
              {addMsg.type === "ok" ? <CheckCircle size={16} /> : <XCircle size={16} />}
              <span>{addMsg.text}</span>
            </div>
            {addMsg.type === "ok" && addMsg.newAccId && (
              <Btn
                variant="solid"
                className="h-7 text-[11.5px] bg-ok/20 border-ok/40 hover:bg-ok/30 text-fg"
                icon={<Play size={12} weight="fill" />}
                onClick={() => void handleWake(addMsg.newAccId!)}
              >
                Mo trinh duyet dang nhap
              </Btn>
            )}
          </div>
        )}
      </div>

      {/* Account List */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13.5px] font-bold text-fg flex items-center gap-2">
            Danh sach Tai khoan ({accounts.length})
          </h3>
          <Btn variant="ghost" className="h-7 text-[11.5px]" onClick={onRefreshPool}>
            <ArrowClockwise size={13} />
            Lam moi danh sach
          </Btn>
        </div>

        {accounts.length === 0 ? (
          <div className="rounded-panel border border-dashed border-line2 p-8 text-center text-[12.5px] text-mut">
            Chua co tai khoan nao trong pool. Hay them mot account moi o tren!
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {accounts.map((a) => {
              const busyAction = busyAcc[a.id];
              const flowStatus = probedDetails[a.id];
              const isCooling = a.cooldown_remaining_s > 0;

              return (
                <div
                  key={a.id}
                  className={`flex flex-col gap-2.5 rounded-ctl border p-3.5 transition-colors ${
                    !a.enabled
                      ? "border-line2/40 bg-panel/40 opacity-70"
                      : a.running
                      ? "border-ok/40 bg-panel2/80"
                      : "border-line2 bg-panel2/50"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[13.5px] font-bold text-fg">{a.id}</span>
                      <span className="font-mono text-[11px] text-mut rounded bg-line px-1.5 py-0.5">
                        :{a.cdp_port}
                      </span>

                      {a.running ? (
                        <Chip tone="ok" live={true} title="Trinh duyet CloakBrowser dang mo">
                          Dang mo
                        </Chip>
                      ) : (
                        <Chip tone="neutral" title="Dang dong de tiet kiem RAM">
                          Standby
                        </Chip>
                      )}

                      {!a.enabled ? (
                        <Chip tone="err" title="Account bi tat tam thoi, khong duoc phan viec">
                          Tat
                        </Chip>
                      ) : isCooling ? (
                        <Chip tone="warn" title={a.cooldown_reason ?? "Dang tam dung bao ve chong abuse"}>
                          Cooldown {Math.ceil(a.cooldown_remaining_s / 60)}'
                        </Chip>
                      ) : (
                        <Chip tone="ok">San sang</Chip>
                      )}

                      {a.role === "active" && (
                        <span className="rounded bg-acc/20 px-1.5 py-0.5 text-[10.5px] font-bold text-acc">
                          Dang ganh Batch
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      {a.running ? (
                        <Btn
                          variant="ghost"
                          className="h-7 text-[11.5px] border-warn/40 text-warn hover:bg-warn/10"
                          busy={busyAction === "hibernate"}
                          icon={<Stop size={12} weight="fill" />}
                          onClick={() => void handleHibernate(a.id)}
                          title="Dong trinh duyet de giai phong RAM"
                        >
                          Dong
                        </Btn>
                      ) : (
                        <Btn
                          variant="solid"
                          className="h-7 text-[11.5px] text-fg hover:border-acc/50"
                          busy={busyAction === "wake"}
                          icon={<Play size={12} weight="fill" className="text-acc" />}
                          onClick={() => void handleWake(a.id)}
                          title="Mo trinh duyet co giao dien de dang nhap Google Flow"
                        >
                          Mo dang nhap
                        </Btn>
                      )}

                      <Btn
                        variant="ghost"
                        className="h-7 text-[11.5px]"
                        busy={busyAction === "probe"}
                        icon={<ArrowClockwise size={12} />}
                        onClick={() => void handleProbe(a.id)}
                        title="Kiem tra xem tab Flow da mo va dang o project nao"
                      >
                        Kiem tra
                      </Btn>

                      {isCooling && (
                        <Btn
                          variant="ghost"
                          className="h-7 text-[11.5px] text-warn"
                          busy={busyAction === "reset"}
                          onClick={() => void handleResetCooldown(a.id)}
                          title="Xoa thoi gian cho cooldown"
                        >
                          Reset
                        </Btn>
                      )}

                      <Btn
                        variant="ghost"
                        className="h-7 text-[11.5px]"
                        busy={busyAction === "toggle"}
                        onClick={() => void handleToggleEnabled(a)}
                        title={a.enabled ? "Tam ngung account nay" : "Bat lai account nay"}
                      >
                        <Power size={13} className={a.enabled ? "text-ok" : "text-mut"} />
                      </Btn>

                      <Btn
                        variant="danger"
                        className="h-7 px-2"
                        busy={busyAction === "delete"}
                        onClick={() => setDeleteConfirm({ id: a.id, deleteVault: false })}
                        title="Xoa khoi Pool"
                      >
                        <Trash size={13} />
                      </Btn>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-mut border-t border-line2/50 pt-2">
                    <div className="flex items-center gap-3">
                      <span>
                        Profile: <code className="text-dim">{a.profile_id}</code>
                      </span>
                      {a.note && <span className="text-dim italic">"{a.note}"</span>}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-ok">OK {a.total_completed} thanh cong</span>
                      <span className="text-err">X {a.total_rejected} tu choi</span>
                      {a.last_error && (
                        <span className="text-warn max-w-[200px] truncate" title={a.last_error}>
                          Loi: {a.last_error}
                        </span>
                      )}
                    </div>
                  </div>

                  {flowStatus && (
                    <div className="rounded border border-line bg-panel p-2.5 text-[11.5px] flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-fg">Ket qua kiem tra phien:</span>
                        {flowStatus.cdp_ok ? (
                          <span className="text-ok flex items-center gap-1 font-semibold">
                            <CheckCircle size={13} /> CDP phan hoi tot
                          </span>
                        ) : (
                          <span className="text-err flex items-center gap-1 font-semibold">
                            <XCircle size={13} /> CDP chua phan hoi
                          </span>
                        )}
                      </div>
                      {flowStatus.flow_tab_url ? (
                        <p className="text-dim">
                          Tab: <span className="font-mono text-[11px] text-fg">{flowStatus.flow_tab_url}</span>
                        </p>
                      ) : (
                        <p className="text-warn">
                          Chua thay tab Flow nao dang mo. Hay bam "Mo dang nhap" va vao flow.google.com!
                        </p>
                      )}
                      {flowStatus.flow_project_id && (
                        <p className="text-dim">
                          Active Project:{" "}
                          <span className="font-mono text-[11px] text-acc">{flowStatus.flow_project_id}</span>
                        </p>
                      )}
                      {flowStatus.error && (
                        <p className="text-err font-mono text-[11px]">{flowStatus.error}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pool Tuning */}
      <div className="rounded-panel border border-line2 bg-panel2 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Sliders size={16} className="text-acc" weight="bold" />
          <h3 className="text-[13.5px] font-bold text-fg">Cau hinh Tai & Gioi han RAM cua Pool</h3>
        </div>

        <form onSubmit={handleSaveConfig} className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[11.5px] font-semibold text-dim">
                Dinh muc anh tren moi account (Q_target)
              </label>
              <input
                type="number"
                min={1}
                max={200}
                value={targetJobs}
                onChange={(e) => setTargetJobs(Number(e.target.value) || 25)}
                className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12.5px] text-fg focus:border-acc/70 focus:outline-none font-mono"
              />
              <p className="mt-1 text-[11px] text-mut">
                Mac dinh 25 anh/account. Giup Wear-leveling xoay tua va tranh loang bo nho cache i2i.
              </p>
            </div>

            <div>
              <label className="mb-1 block text-[11.5px] font-semibold text-dim">
                Tran trinh duyet chay song song toi da (M_RAM)
              </label>
              <input
                type="number"
                min={1}
                max={16}
                value={maxRam}
                onChange={(e) => setMaxRam(Number(e.target.value) || 4)}
                className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12.5px] text-fg focus:border-acc/70 focus:outline-none font-mono"
              />
              <p className="mt-1 text-[11px] text-mut">
                Mac dinh 4 browser. Moi CloakBrowser chiem khoang 500MB RAM.
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            {configMsg ? (
              <span
                className={`text-[12px] font-medium ${
                  configMsg.type === "ok" ? "text-ok" : "text-err"
                }`}
              >
                {configMsg.text}
              </span>
            ) : <span />}

            <Btn variant="solid" type="submit" busy={saveConfigBusy} className="h-8 text-[12.5px]">
              Luu cau hinh
            </Btn>
          </div>
        </form>
      </div>

      {/* Delete confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="flex w-full max-w-md flex-col gap-4 rounded-panel border border-line2 bg-panel p-5 shadow-2xl">
            <div className="flex items-center gap-3 text-err">
              <Warning size={24} weight="bold" />
              <h4 className="text-[15px] font-bold text-fg">Xac nhan xoa tai khoan?</h4>
            </div>

            <p className="text-[12.5px] text-dim leading-relaxed">
              Ban co chac muon xoa account <code className="font-bold text-fg font-mono">{deleteConfirm.id}</code> khoi
              pool dieu phoi?
            </p>

            <label className="flex items-center gap-2 text-[12px] text-err/90 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={deleteConfirm.deleteVault}
                onChange={(e) =>
                  setDeleteConfirm((prev) => (prev ? { ...prev, deleteVault: e.target.checked } : null))
                }
                className="size-4 rounded accent-err"
              />
              <span>Dong thoi xoa thu muc luu tru profile trong <code>browser_vault/</code></span>
            </label>

            <div className="flex items-center justify-end gap-2 pt-2">
              <Btn variant="ghost" onClick={() => setDeleteConfirm(null)}>
                Huy bo
              </Btn>
              <Btn variant="danger" onClick={() => void handleConfirmDelete()}>
                Xoa Account
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
