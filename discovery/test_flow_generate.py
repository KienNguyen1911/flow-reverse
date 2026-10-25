import time
from playwright.sync_api import sync_playwright

clean_prompt = """A photorealistic, candid lifestyle fashion portrait of the exact young Korean woman from @main-model.jpg, perfectly trying on and wearing the complete outfit and posing in the exact scene from @1.jpg, vertical 3:4 aspect ratio.

[Identity Lock]: The exact young Korean woman from @main-model.jpg, strictly preserving her facial proportions, soft oval face shape, delicate jawline, natural almond-shaped eyes with subtle aegyo-sal, gentle captivating smile, and dark chestnut hair styled with wispy see-through bangs cascading softly down her shoulders.

[Exact Garment Specification]: She wears the exact outfit from @1.jpg:
- Outerwear: A long-sleeve, cropped light seafoam/mint-blue textured ribbed-knit shrug cardigan worn open.
- Dress: A fitted cream-white floral-jacquard mini slip dress with spaghetti straps, a soft scoop neckline tied with a delicate front ribbon string, and an airy, subtly flared hem falling mid-thigh.
- Accessories: A small pastel lilac-pink leather shoulder bag tucked snugly under her left arm, jade green bangle bracelet, beige flat Mary Jane shoes.

[Environment]: Full-body shot. She stands naturally in the warm, ambient-lit supermarket bakery section, posing beside the rustic wooden pastry display cart filled with French baguettes under the glass showcase.

[Anti-AI Realism Modifiers]: Raw candid 35mm photography / iPhone 16 Pro natural lifestyle shot, visible skin micro-pores, authentic fabric weave texture, natural lighting falloff, subtle film grain, zero plastic skin smoothing."""

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Flow page:", p.url)
                
                # Snapshot existing images before generate
                before_imgs = p.evaluate("""() => {
                    const imgs = Array.from(document.querySelectorAll('img')).map(i => i.src);
                    return Array.from(new Set(imgs));
                }""")
                print("Images before generate:", len(before_imgs))

                # Clear and enter prompt
                textarea = p.query_selector('textarea, div[contenteditable="true"]')
                if not textarea:
                    print("Textarea not found")
                    exit(1)
                
                textarea.click()
                p.keyboard.press("Control+A")
                p.keyboard.press("Backspace")
                p.wait_for_timeout(300)

                # Type ingredients with @
                p.keyboard.type("@main-model", delay=50)
                p.wait_for_timeout(500)
                p.keyboard.press("Enter")
                p.wait_for_timeout(300)

                p.keyboard.type(" @1.jpg", delay=50)
                p.wait_for_timeout(500)
                p.keyboard.press("Enter")
                p.wait_for_timeout(300)

                # Type rest of prompt
                p.keyboard.type(" " + clean_prompt, delay=10)
                p.wait_for_timeout(1000)

                # Click generate button
                gen_btn = p.query_selector('button[aria-label*="Bắt đầu tạo"], button:has-text("Bắt đầu tạo")')
                print("Generate button found:", gen_btn is not None)
                if gen_btn:
                    gen_btn.click()
                    print("Clicked 'Bắt đầu tạo'!")
                    p.wait_for_timeout(5000)
                    p.screenshot(path='out/flow_generating.png')
                    print("Saved out/flow_generating.png!")
                break
