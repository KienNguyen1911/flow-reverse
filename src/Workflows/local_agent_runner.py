"""Local Agent Runner — Invokes local AI coding agents (`agy` and `pi`) via subprocess asynchronously."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "configs" / "agent_config.json"


@dataclass
class LocalAgentConfig:
    preferred_agent: str = "agy"  # "agy" | "pi"
    agy_model: str = "gemini-3.8-flash-low"
    pi_model: str = "agnes-3.0-flash"
    timeout_s: float = 75.0

    def to_dict(self) -> dict:
        return asdict(self)


def load_agent_config() -> LocalAgentConfig:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return LocalAgentConfig(
                preferred_agent=data.get("preferred_agent", "agy"),
                agy_model=data.get("agy_model", "gemini-3.8-flash-low"),
                pi_model=data.get("pi_model", "agnes-3.0-flash"),
                timeout_s=float(data.get("timeout_s", 75.0)),
            )
        except Exception:
            pass
    return LocalAgentConfig()


def save_agent_config(cfg: LocalAgentConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def find_agent_binary(agent_name: str) -> Optional[str]:
    """Find absolute path to local agent binary."""
    name = agent_name.lower().strip()
    if name == "agy":
        cand = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
        if cand.is_file():
            return str(cand)
        w = shutil.which("agy")
        if w:
            return w
    elif name == "pi":
        cand = Path(os.environ.get("APPDATA", "")) / "npm" / "pi.cmd"
        if cand.is_file():
            return str(cand)
        w = shutil.which("pi")
        if w:
            return w
    return None


def extract_clean_prompt_from_agent_output(raw_output: str) -> str:
    """Extract clean generation prompt from markdown response of the agent."""
    if not raw_output or not raw_output.strip():
        return ""

    text = raw_output.strip()

    # 1. Search for fenced codeblocks - pick the best one
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_blocks:
        # Filter out empty or tiny blocks, prefer the one with substantial length
        valid_blocks = [b.strip() for b in code_blocks if len(b.strip()) > 30]
        if valid_blocks:
            # Prefer block that contains policy or fashion keywords, or longest
            for b in valid_blocks:
                if "fictional" in b.lower() or "lookbook" in b.lower() or "prompt" in b.lower():
                    return b
            return max(valid_blocks, key=len)

    # 2. Look for labelled prompt chunks (e.g. Positive Prompt:, Video Prompt 1:, etc.)
    label_match = re.search(
        r"(?:(?:positive\s+)?prompt(?:(?:\s*#?\s*[0-9]+|\s*\(?[0-9]+\)?))?|prompt)\s*[:\-–]\s*([^\n\r]+(?:\n(?!\n|\*|#).*)*)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        cand = label_match.group(1).strip().strip('"').strip("'").strip("`")
        if len(cand) > 30:
            return cand

    # 3. Fallback: filter conversational lines
    lines = text.splitlines()
    filtered: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(?:💡|hướng\s*dẫn|lưu\s*ý\b|note\b|cách\s*dùng\b|usage\b)", s, re.IGNORECASE):
            break
        if re.match(
            r"^(?:dưới đây|đây là|tôi đã|chào|hello|hi\b|sure|here|certainly|okay|ok\b)",
            s,
            re.IGNORECASE,
        ):
            continue
        if re.match(
            r"^(?:hope|let me know|bạn có thể|chúc bạn|hãy cho tôi biết)",
            s,
            re.IGNORECASE,
        ):
            continue
        filtered.append(line)

    res = "\n".join(filtered).strip().strip('"').strip("'")
    return res or text


class LocalAgentRunner:
    """Executes prompt generation requests using local agy or pi CLI."""

    def __init__(self, config: Optional[LocalAgentConfig] = None):
        self.config = config or load_agent_config()

    async def run_prompt_instruction(
        self,
        instruction: str,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> str:
        """Execute a single-turn non-interactive prompt through local agent CLI."""
        target_agent = (agent or self.config.preferred_agent or "agy").lower()
        timeout = timeout_s or self.config.timeout_s

        bin_path = find_agent_binary(target_agent)
        if not bin_path:
            raise FileNotFoundError(
                f"Không tìm thấy công cụ AI Agent '{target_agent}' trên máy tính. "
                "Hãy kiểm tra xem 'agy' hoặc 'pi' đã được cài đặt chưa."
            )

        if target_agent == "agy":
            chosen_model = model or self.config.agy_model or "gemini-3.8-flash-low"
            cmd = [bin_path, "--dangerously-skip-permissions", "--model", chosen_model, "-p", instruction]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT),
            )
        elif target_agent == "pi":
            # For Windows .cmd files
            cmd = ["cmd.exe", "/c", bin_path, "--no-session", "--no-tools", "-p", instruction]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT),
            )
        else:
            raise ValueError(f"Agent không được hỗ trợ: {target_agent}")

        try:
            stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise TimeoutError(f"Local Agent '{target_agent}' xử lý quá thời gian ({timeout}s).")

        stdout_text = stdout_data.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_data.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            err_msg = stderr_text or stdout_text or f"Mã lỗi thoát {proc.returncode}"
            raise RuntimeError(f"Local Agent '{target_agent}' báo lỗi: {err_msg}")

        return extract_clean_prompt_from_agent_output(stdout_text)

    async def test_agent(self, agent_name: Optional[str] = None) -> dict:
        """Probe local agent CLI to verify availability and latency."""
        target = (agent_name or self.config.preferred_agent or "agy").lower()
        bin_path = find_agent_binary(target)
        if not bin_path:
            return {
                "ok": False,
                "agent": target,
                "latency_ms": 0,
                "message": f"Không tìm thấy thực thi của '{target}'.",
            }

        t0 = time.perf_counter()
        try:
            res = await self.run_prompt_instruction(
                instruction="Trả lời ngắn gọn đúng 1 từ: AGENT_OK",
                agent=target,
                timeout_s=25.0,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            return {
                "ok": True,
                "agent": target,
                "latency_ms": elapsed_ms,
                "message": f"{target.upper()} sẵn sàng phản hồi ({elapsed_ms}ms).",
                "sample_response": res[:60],
            }
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            return {
                "ok": False,
                "agent": target,
                "latency_ms": elapsed_ms,
                "message": f"Lỗi khi gọi {target}: {e}",
            }


# Global runner
_runner: Optional[LocalAgentRunner] = None


def get_agent_runner() -> LocalAgentRunner:
    global _runner
    if _runner is None:
        _runner = LocalAgentRunner()
    return _runner
