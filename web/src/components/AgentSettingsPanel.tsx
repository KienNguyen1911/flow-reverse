import { useEffect, useState } from "react";
import {
  CheckCircle,
  Cpu,
  FileCode,
  FloppyDisk,
  Lightning,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { AgentSkillInfo, LocalAgentConfig, TestAgentResponse } from "../types";
import { Chip, Spinner } from "./ui";

const AGY_MODELS = [
  { id: "gemini-3.8-flash-low", label: "Gemini 3.8 Flash (Low) — Siêu tốc, khuyên dùng" },
  { id: "gemini-3.8-flash-medium", label: "Gemini 3.8 Flash (Medium)" },
  { id: "gemini-3.8-flash-high", label: "Gemini 3.8 Flash (High) — Suy luận kỹ" },
  { id: "gemini-4-argon-medium", label: "Gemini 4 Argon (Medium)" },
  { id: "claude-sonnet-5-5-medium", label: "Claude Sonnet 5.5 (Medium)" },
];

export function AgentSettingsPanel() {
  const [config, setConfig] = useState<LocalAgentConfig>({
    preferred_agent: "agy",
    agy_model: "gemini-3.8-flash-low",
    pi_model: "agnes-3.0-flash",
    timeout_s: 75,
  });
  const [skills, setSkills] = useState<AgentSkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestAgentResponse | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.agentConfig(), api.agentSkills()])
      .then(([cfg, sData]) => {
        if (!mounted) return;
        if (cfg) setConfig(cfg);
        if (sData?.skills) setSkills(sData.skills);
      })
      .catch((err) => console.error("Lỗi nạp cấu hình Agent:", err))
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      const res = await api.setAgentConfig(config);
      if (res.ok) {
        setConfig(res.config);
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err: any) {
      alert(`Lỗi lưu cấu hình: ${err?.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestAgent = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testAgent(config.preferred_agent);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        ok: false,
        agent: config.preferred_agent,
        latency_ms: 0,
        message: err?.message || String(err),
      });
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size={24} />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <Cpu size={22} className="text-acc" weight="duotone" />
          <h2 className="text-[17px] font-bold text-fg">AI Prompt Agent (Cục bộ)</h2>
          <Chip tone="ok">Hoàn toàn Offline / Local CLI</Chip>
        </div>
        <p className="mt-1 text-[12px] text-mut leading-relaxed">
          Sử dụng trực tiếp các công cụ AI Agent có sẵn trên máy (<strong>agy</strong> hoặc{" "}
          <strong>pi</strong>) để tự động phân tích ảnh kết quả và sinh prompt bám sát quy chuẩn
          chính sách của Google Flow. Không tốn phí API bên ngoài.
        </p>
      </div>

      {/* Main Settings Card */}
      <div className="rounded-panel border border-line2 bg-panel p-5 space-y-5">
        <h3 className="text-[13px] font-bold text-fg flex items-center gap-2">
          <Sparkle size={15} className="text-acc" />
          <span>Cấu hình Công cụ Thực thi</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Agent Selection */}
          <div className="space-y-1.5">
            <label className="text-[11.5px] font-semibold text-dim">Chọn AI Agent trên máy</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setConfig({ ...config, preferred_agent: "agy" })}
                className={`p-3 rounded-ctl border text-left transition-all ${
                  config.preferred_agent === "agy"
                    ? "border-acc bg-acc/10 text-fg shadow-sm shadow-acc/10"
                    : "border-line2 bg-panel2 text-dim hover:border-line"
                }`}
              >
                <div className="text-[12.5px] font-bold flex items-center justify-between">
                  <span>agy CLI</span>
                  {config.preferred_agent === "agy" && (
                    <span className="size-2 rounded-full bg-acc" />
                  )}
                </div>
                <p className="text-[10px] text-mut mt-0.5">Antigravity CLI (Khuyên dùng)</p>
              </button>

              <button
                type="button"
                onClick={() => setConfig({ ...config, preferred_agent: "pi" })}
                className={`p-3 rounded-ctl border text-left transition-all ${
                  config.preferred_agent === "pi"
                    ? "border-acc bg-acc/10 text-fg shadow-sm shadow-acc/10"
                    : "border-line2 bg-panel2 text-dim hover:border-line"
                }`}
              >
                <div className="text-[12.5px] font-bold flex items-center justify-between">
                  <span>pi CLI</span>
                  {config.preferred_agent === "pi" && (
                    <span className="size-2 rounded-full bg-acc" />
                  )}
                </div>
                <p className="text-[10px] text-mut mt-0.5">Pi Coding Agent (npm)</p>
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div className="space-y-1.5">
            <label className="text-[11.5px] font-semibold text-dim">
              Mô hình ({config.preferred_agent.toUpperCase()})
            </label>
            {config.preferred_agent === "agy" ? (
              <select
                value={config.agy_model}
                onChange={(e) => setConfig({ ...config, agy_model: e.target.value })}
                className="w-full h-10 rounded-ctl border border-line2 bg-panel2 px-3 text-[12px] text-fg focus:border-acc outline-none"
              >
                {AGY_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={config.pi_model}
                onChange={(e) => setConfig({ ...config, pi_model: e.target.value })}
                placeholder="agnes-3.0-flash"
                className="w-full h-10 rounded-ctl border border-line2 bg-panel2 px-3 text-[12px] text-fg focus:border-acc outline-none font-mono"
              />
            )}
            <p className="text-[10px] text-mut">
              Model được dùng để phân tích ảnh và sinh prompt qua cờ non-interactive.
            </p>
          </div>
        </div>

        {/* Timeout Slider */}
        <div className="pt-2 border-t border-line/60 flex items-center justify-between">
          <div>
            <span className="text-[11.5px] font-semibold text-dim">Thời gian chờ tối đa (Timeout)</span>
            <p className="text-[10px] text-mut">Thời gian tự động ngắt nếu agent bị treo.</p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={15}
              max={300}
              value={config.timeout_s}
              onChange={(e) => setConfig({ ...config, timeout_s: Number(e.target.value) || 60 })}
              className="w-20 h-8 rounded-ctl border border-line2 bg-panel2 px-2 text-[12px] text-center text-fg font-mono"
            />
            <span className="text-[11px] text-mut">giây</span>
          </div>
        </div>

        {/* Action Buttons: Test & Save */}
        <div className="flex items-center justify-between pt-3 border-t border-line/60">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestAgent}
              disabled={testing}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-semibold text-fg hover:border-acc/70 transition-colors disabled:opacity-40"
            >
              {testing ? <Spinner size={12} /> : <Lightning size={14} className="text-acc" />}
              <span>Kiểm tra kết nối</span>
            </button>

            {testResult && (
              <span
                className={`text-[11px] inline-flex items-center gap-1 font-medium ${
                  testResult.ok ? "text-ok" : "text-err"
                }`}
              >
                {testResult.ok ? <CheckCircle size={13} /> : <Warning size={13} />}
                <span>{testResult.message}</span>
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 h-8 px-4 rounded-ctl bg-acc text-accink text-[12px] font-bold hover:bg-acc2 transition-colors disabled:opacity-40"
          >
            {saving ? <Spinner size={12} /> : <FloppyDisk size={14} weight="fill" />}
            <span>{saveSuccess ? "Đã lưu!" : "Lưu cấu hình"}</span>
          </button>
        </div>
      </div>

      {/* Discovered Skills Catalog */}
      <div className="rounded-panel border border-line2 bg-panel p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-bold text-fg flex items-center gap-2">
            <FileCode size={16} className="text-acc" />
            <span>Kho Kỹ năng Quy chuẩn (`prompt-skills/`)</span>
          </h3>
          <span className="text-[11px] font-mono text-mut">{skills.length} skills</span>
        </div>

        <div className="space-y-3">
          {skills.map((s) => (
            <div
              key={s.id}
              className="p-3.5 rounded-ctl border border-line2 bg-panel2/60 space-y-1.5 hover:border-line transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12.5px] font-bold text-fg">{s.name}</span>
                <span className="font-mono text-[10px] text-mut bg-panel px-2 py-0.5 rounded border border-line2">
                  {s.file_path}
                </span>
              </div>
              <p className="text-[11px] text-dim leading-relaxed">{s.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
