import re
import sys
sys.path.insert(0, ".")
from src.Bridge.gemini_bridge import parse_gemini_image_prompt


text = """Dưới đây là 2 phiên bản prompt được thiết kế riêng cho công cụ Virtual Try-On / Model Swap trên Google Flow (flow.google.com), giúp chuyển giao trọn vẹn khuôn mặt người mẫu cố định (Nabi) từ Ảnh 1 sang bộ trang phục, dáng đứng và không gian quầy bánh mì từ Ảnh 2:

Bản 1: Direct Flow Transfer Prompt (Ngắn gọn, trực diện)
Markdown
Model swap and character try-on task: Keep the exact outfit, body pose, framing, lighting, and bakery supermarket background from the reference photo (Image 2), but replace the woman's face and personal identity entirely with the fixed model from Image 1.

- Model Identity: Apply the exact face, delicate soft jawline, almond-shaped eyes with subtle aegyo-sal, dewy glass skin texture with visible micro-pores, and dark hazel-brown hair with wispy see-through bangs from Image 1.
- Outfit to strictly preserve: The light mint/seafoam-blue textured ribbed-knit cropped shrug cardigan worn open over the sleeveless cream-white floral-patterned mini camisole slip dress featuring a delicate front chest bow-tie; complete with the soft pastel pink shoulder bag tucked under her arm, green jade bangle, and beige Mary Jane flat shoes.
- Scene & Pose: Preserve the exact relaxed standing pose next to the wooden baguette bakery cart ("BÁNH MÌ BAGUETTE") inside the grocery aisle, with realistic ambient store lighting and natural skin tones. Seamlessly blend features without distortion.

Bản 2: Detailed Realism Try-On Prompt (Chuyên sâu, khử da nhựa AI & chi tiết chân thực)
Markdown
A photorealistic, candid lifestyle fashion portrait of the exact young Korean woman from Image 1, perfectly trying on and wearing the complete outfit and posing in the exact scene from Image 2, vertical 3:4 aspect ratio.

[Identity Lock]: The exact young Korean woman from Image 1, strictly preserving her facial proportions, soft oval face shape, delicate jawline, natural almond-shaped eyes with subtle aegyo-sal, gentle captivating smile, and dark chestnut hair styled with wispy see-through bangs cascading softly down her shoulders.

[Exact Garment Specification]: She wears the exact outfit from Image 2:
- Outerwear: A long-sleeve, cropped light seafoam/mint-blue textured ribbed-knit shrug cardigan worn open.
- Dress: A fitted cream-white floral-jacquard mini slip dress with spaghetti straps, a soft scoop neckline tied with a delicate front ribbon string, and an airy, subtly flared hem falling mid-thigh.
- Accessories & Footwear: A small pastel lilac-pink leather shoulder bag tucked snugly under her left arm, a jade green bangle bracelet on her wrist, a dainty minimalist necklace, and beige flat Mary Jane shoes with delicate cross-straps and tiny bows.

[Environment & Framing]: Full-body shot. She stands naturally in the warm, ambient-lit supermarket bakery section, posing beside the rustic wooden pastry display cart filled with French baguettes under the glass showcase, with modern gray slat partitions and softly blurred grocery shelves in the background.

[Anti-AI Realism Modifiers]: Raw candid 35mm photography / iPhone 16 Pro natural lifestyle shot, visible skin micro-pores, authentic fabric weave texture, natural lighting falloff, subtle film grain, zero plastic skin smoothing, no artificial studio gloss.

💡 Hướng dẫn thao tác trên flow.google.com:

Ô 1 (Identity Anchor): Nạp ảnh chân dung người mẫu gốc Ảnh 1 (1792955358411_main-model_2515fb.jpg).

Ô 2 (Pose & Garment Reference): Nạp ảnh mẫu mặc outfit quầy bánh mì Ảnh 2 (1792955345724_1_2515fb.jpg).

Dán một trong hai prompt trên vào ô câu lệnh để hệ thống tiến hành hoán đổi mặt, giữ trọn vẹn từng chi tiết nơ áo, chất vải len dệt kim và bối cảnh quầy bánh."""

def parse_gemini_image_prompt_new(raw_text: str) -> str:
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text.strip()

    # 1. Look for fenced codeblock
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_blocks:
        candidate = code_blocks[0].strip()
        if len(candidate) > 20:
            return candidate

    # 2. Look for Vietnamese/English dual prompt versions: Bản 2 (prefer detailed) or Bản 1
    m_ban2 = re.search(
        r"(?:bản\s*2|option\s*2|phiên\s*bản\s*2)[^\n:]*[:\-–]?(.*?)(?=(?:💡|hướng dẫn|lưu ý|note:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_ban2:
        chunk = m_ban2.group(1).strip()
        chunk = re.sub(r"^[^\n]*\n(?:markdown\s*\n)?", "", chunk, flags=re.IGNORECASE).strip()
        if len(chunk) > 30:
            return chunk

    m_ban1 = re.search(
        r"(?:bản\s*1|option\s*1|phiên\s*bản\s*1)[^\n:]*[:\-–]?(.*?)(?=(?:bản\s*2|option\s*2|💡|hướng dẫn|lưu ý|note:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_ban1:
        chunk = m_ban1.group(1).strip()
        chunk = re.sub(r"^[^\n]*\n(?:markdown\s*\n)?", "", chunk, flags=re.IGNORECASE).strip()
        if len(chunk) > 30:
            return chunk

    return "fallback"

res = parse_gemini_image_prompt_new(text)
print("=== PARSED LENGTH ===", len(res))
print("=== STARTS WITH ===")
print(res[:200])
print("=== ENDS WITH ===")
print(res[-200:])

