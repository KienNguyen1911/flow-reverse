from pathlib import Path
from src.Bridge.gemini_bridge import GeminiNotebookBridge, parse_gemini_video_prompts

first_frame = Path("out/first_frame_generated.png").resolve()

print("Connecting to Gemini on port 4023...")
with GeminiNotebookBridge(cdp_url="http://127.0.0.1:4023") as gemini:
    print("Uploading first_frame.png...")
    gemini.upload_files([first_frame])
    print("Sending '@try-on-prompt create video prompt'...")
    raw = gemini.send_prompt("@try-on-prompt create video prompt", wait_timeout_s=90.0)
    print("=== RAW RESPONSE ===")
    print(raw)
    p1, p2 = parse_gemini_video_prompts(raw)
    print("=== VIDEO PROMPT 1 (8s) ===")
    print(p1)
    print("=== VIDEO PROMPT 2 (8s) ===")
    print(p2)
    Path("out/vp1.txt").write_text(p1, encoding="utf-8")
    Path("out/vp2.txt").write_text(p2, encoding="utf-8")
