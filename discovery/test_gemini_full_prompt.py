from pathlib import Path
from src.Bridge.gemini_bridge import GeminiNotebookBridge

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

print("Opening GeminiNotebookBridge on port 4023...")
with GeminiNotebookBridge(cdp_url="http://127.0.0.1:4023") as gemini:
    print("Uploading 2 images...")
    gemini.upload_files([model_img, garment_img])
    print("Sending prompt with Enter on skill tag...")
    # Send prompt with explicit Enter after @try-on-prompt
    res = gemini.send_prompt("@try-on-prompt create image prompt", wait_timeout_s=90.0)
    print("=== GEMINI FULL RESPONSE ===")
    print(res)
