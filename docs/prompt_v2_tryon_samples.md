# Mẫu prompt try-on V2 để test

Ba biến thể, cùng một bộ trang phục (áo knit lệch vai + chân váy bong bóng + tất cao cổ + sneaker).
Dùng đúng thứ tự ảnh: **Ảnh 1 = model (identity)**, **Ảnh 2 = garment**, **Ảnh 3 = background** (tuỳ chọn).

Sinh mỗi biến thể 2–3 lần, giữ nguyên model/thiết lập, rồi chấm theo thứ tự: identity → garment →
anatomy → presentation (`docs/prompt_v2_tryon.md` §6).

## 1. Bản chính — 3 ảnh, Mode A (ba phần tư)

Dùng cho so sánh trực tiếp với V1: cùng Ảnh 1/2/3, cùng model sinh ảnh.

```text
Try-on photograph of the exact same model from Image 1, wearing the exact garment from Image 2.

[IDENTITY LOCK]
Preserve the facial identity from Image 1 exactly: East Asian facial features, soft delicate eye shape, natural nose structure, natural lips, messy high bun with face-framing wispy strands, natural skin texture. Same person, same face, same age as Image 1. Do not beautify, slim, symmetrise or age the face, and do not change the hairstyle.

[GARMENT FIDELITY]
Reproduce the complete outfit from Image 2 exactly: beige draped asymmetrical off-shoulder long-sleeve knit top with ruched fabric texture, high-waisted charcoal grey voluminous pleated bubble skirt, charcoal grey knee-high socks, metallic silver chunky running sneakers. Copy only what the reference shows: seams, weave, trims, hardware and branding that are physically part of the garment are reproduced; anything hidden behind the body, hair or another layer is not invented, extended or restyled. Where this description and Image 2 disagree, Image 2 wins. Do not redesign, simplify, replace, omit, recolour or re-proportion any element, and do not improve the outfit for the photograph.

[ANATOMY & POSE]
Preserve the model's exact body proportions, height and silhouette from Image 1: long unbroken leg line, visible waist-to-hip transition, natural anatomical proportions, no shortening of the torso, no widening of the shoulders, no limb stretching. Body turned about thirty to forty-five degrees away from the camera so the silhouette reads tall and narrow, shoulders and hips presented at a three-quarter angle instead of square-on, near shoulder lower than the far shoulder, weight settled on the back leg, the front foot placed forward without crossing the body's vertical centerline, one arm relaxed away from the torso to keep the waistline visible. Head turned gently back toward the camera on the neck, so the face stays readable while the torso keeps its three-quarter angle; eyes toward the lens or just beside it, chin level. Natural stance: the two legs clearly separated and individually readable from hip to ankle, both feet fully visible and grounded, knees relaxed rather than locked or deeply bent.

[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the exact head-to-body ratio, leg-to-torso ratio and limb lengths visible in Image 1; that body is the only proportion reference. Convey height through upright posture, clear leg separation, framing and camera distance, never through redrawn proportions. Do not lengthen the legs, shorten the torso, narrow the waist, widen the shoulders or stretch the neck.
Camera Perspective: full-body fashion photography, camera at waist level with a three-degree upward tilt, horizon level, and the same subject-to-camera distance across every image in the set. Perspective is set by that distance: stand back far enough that the whole figure fits a 50mm-equivalent frame with natural scale from crown to sole. Avoid steep low angles, high angles, downward tilt and strong foreshortening.
Lens: 50mm equivalent field of view as the aesthetic target; focal length alone does not compress or elongate anything, so keep the camera distance constant and the feet never read oversized while the legs never read shortened. No wide-angle distortion.
Composition: clean vertical full-body editorial composition. Crown of the head 12 percent below the top edge, soles of the shoes 12 percent above the bottom edge, figure filling 76 percent of the frame height. Both feet fully visible and grounded, model centred on the vertical axis of the frame, subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, neck lengthened by posture rather than anatomy, balanced pelvis. No forced shoulder elevation, torso compression or exaggerated body curvature.
Visual Silhouette: one continuous vertical line from the shoulders through the waist, hips, knees and ankles, with thighs, knees, calves and ankles individually distinguishable and the two legs never merging into one mass. No horizontal band from hem, sock line or waistband cuts the figure in half. The outfit keeps its own design, cut, fit, drape and styling.
Anatomical Integrity: realistic joints, consistent limb lengths and the original body structure from Image 1. No artificial body stretching, disproportionate limbs, distorted feet or distorted joints.
[END HEIGHT & PROPORTION OPTIMIZATION]

[ENVIRONMENT & LIGHTING]
Take only the space, surfaces, ambient light and shadow behaviour from Image 3 — never the person or the garment from Image 3. Bright soft directional daylight, gentle diagonal shadows across the wall and floor plane, realistic light falloff.

[PHOTOGRAPHY AESTHETICS]
Raw candid fashion photography, natural lifestyle editorial aesthetic, realistic skin texture with visible pores and fine facial hair, authentic fabric weave, subtle film grain, natural photographic imperfections. No plastic skin, no HDR glow, no over-sharpening, no AI-smooth texture.

Negative: no altered facial identity, no changed hairstyle, no different face, no plastic or airbrushed skin; no garment redesign, no simplified, recoloured or re-proportioned garment, no missing or added clothing elements, no floating or merged fabric layers, no branding beyond what the reference garment actually carries; no elongated legs, no longer legs, no stretched limbs, no artificial body stretching, no slimmed waist, no widened shoulders, no distorted joints, no distorted or extra feet, no crossed legs, no overlapping thighs, no legs merging into one mass; no high-angle or overhead framing, no steep low-angle distortion, no wide-angle distortion, no oversized feet, no cropped head, no cropped feet, no tilted horizon, no inconsistent subject scale, no zoomed-in torso; no text, no letters, no numbers, no added logos, no watermark, no UI, no card, no label, no price tag, no collage, no split screen, no grid, no border, no frame.
```

## 2. Bản hai ảnh — không có Ảnh 3

Chỉ khác module 5: bối cảnh là studio mô tả sẵn, không kế thừa Ảnh 2.

```text
Try-on photograph of the exact same model from Image 1, wearing the exact garment from Image 2.

[IDENTITY LOCK]
Preserve the facial identity from Image 1 exactly: East Asian facial features, soft delicate eye shape, natural nose structure, natural lips, messy high bun with face-framing wispy strands, natural skin texture. Same person, same face, same age as Image 1. Do not beautify, slim, symmetrise or age the face, and do not change the hairstyle.

[GARMENT FIDELITY]
Reproduce the complete outfit from Image 2 exactly: beige draped asymmetrical off-shoulder long-sleeve knit top with ruched fabric texture, high-waisted charcoal grey voluminous pleated bubble skirt, charcoal grey knee-high socks, metallic silver chunky running sneakers. Copy only what the reference shows: seams, weave, trims, hardware and branding that are physically part of the garment are reproduced; anything hidden behind the body, hair or another layer is not invented, extended or restyled. Where this description and Image 2 disagree, Image 2 wins. Do not redesign, simplify, replace, omit, recolour or re-proportion any element, and do not improve the outfit for the photograph.

[ANATOMY & POSE]
Preserve the model's exact body proportions, height and silhouette from Image 1: long unbroken leg line, visible waist-to-hip transition, natural anatomical proportions, no shortening of the torso, no widening of the shoulders, no limb stretching. Body turned about thirty to forty-five degrees away from the camera so the silhouette reads tall and narrow, shoulders and hips presented at a three-quarter angle instead of square-on, near shoulder lower than the far shoulder, weight settled on the back leg, the front foot placed forward without crossing the body's vertical centerline, one arm relaxed away from the torso to keep the waistline visible. Head turned gently back toward the camera on the neck, so the face stays readable while the torso keeps its three-quarter angle; eyes toward the lens or just beside it, chin level. Natural stance: the two legs clearly separated and individually readable from hip to ankle, both feet fully visible and grounded, knees relaxed rather than locked or deeply bent.

[HEIGHT & PROPORTION OPTIMIZATION]
Body Proportion: preserve the exact head-to-body ratio, leg-to-torso ratio and limb lengths visible in Image 1; that body is the only proportion reference. Convey height through upright posture, clear leg separation, framing and camera distance, never through redrawn proportions. Do not lengthen the legs, shorten the torso, narrow the waist, widen the shoulders or stretch the neck.
Camera Perspective: full-body fashion photography, camera at waist level with a three-degree upward tilt, horizon level, and the same subject-to-camera distance across every image in the set. Perspective is set by that distance: stand back far enough that the whole figure fits a 50mm-equivalent frame with natural scale from crown to sole. Avoid steep low angles, high angles, downward tilt and strong foreshortening.
Lens: 50mm equivalent field of view as the aesthetic target; focal length alone does not compress or elongate anything, so keep the camera distance constant and the feet never read oversized while the legs never read shortened. No wide-angle distortion.
Composition: clean vertical full-body editorial composition. Crown of the head 12 percent below the top edge, soles of the shoes 12 percent above the bottom edge, figure filling 76 percent of the frame height. Both feet fully visible and grounded, model centred on the vertical axis of the frame, subject scale identical across every image in the same set.
Posture: upright spine, relaxed shoulders, neck lengthened by posture rather than anatomy, balanced pelvis. No forced shoulder elevation, torso compression or exaggerated body curvature.
Visual Silhouette: one continuous vertical line from the shoulders through the waist, hips, knees and ankles, with thighs, knees, calves and ankles individually distinguishable and the two legs never merging into one mass. No horizontal band from hem, sock line or waistband cuts the figure in half. The outfit keeps its own design, cut, fit, drape and styling.
Anatomical Integrity: realistic joints, consistent limb lengths and the original body structure from Image 1. No artificial body stretching, disproportionate limbs, distorted feet or distorted joints.
[END HEIGHT & PROPORTION OPTIMIZATION]

[ENVIRONMENT & LIGHTING]
Clean minimalist studio with a curved white cyclorama wall and floor, bright soft directional window-pane daylight casting gentle diagonal shadows across the wall and floor plane, realistic light falloff.

[PHOTOGRAPHY AESTHETICS]
Raw candid fashion photography, natural lifestyle editorial aesthetic, realistic skin texture with visible pores and fine facial hair, authentic fabric weave, subtle film grain, natural photographic imperfections. No plastic skin, no HDR glow, no over-sharpening, no AI-smooth texture.

Negative: no altered facial identity, no changed hairstyle, no different face, no plastic or airbrushed skin; no garment redesign, no simplified, recoloured or re-proportioned garment, no missing or added clothing elements, no floating or merged fabric layers, no branding beyond what the reference garment actually carries; no elongated legs, no longer legs, no stretched limbs, no artificial body stretching, no slimmed waist, no widened shoulders, no distorted joints, no distorted or extra feet, no crossed legs, no overlapping thighs, no legs merging into one mass; no high-angle or overhead framing, no steep low-angle distortion, no wide-angle distortion, no oversized feet, no cropped head, no cropped feet, no tilted horizon, no inconsistent subject scale, no zoomed-in torso; no text, no letters, no numbers, no added logos, no watermark, no UI, no card, no label, no price tag, no collage, no split screen, no grid, no border, no frame.
```

## 3. Bản Mode B — đọc rõ mặt trước trang phục

Dùng khi cần thấy rõ đường cắt ngực, độ rũ của áo và đai eo váy. Chỉ thay module 3; các module còn
lại giữ nguyên như bản 1.

```text
[ANATOMY & POSE]
Preserve the model's exact body proportions, height and silhouette from Image 1: long unbroken leg line, visible waist-to-hip transition, natural anatomical proportions, no shortening of the torso, no widening of the shoulders, no limb stretching. The model stands naturally upright, facing almost directly toward the camera with a subtle five to ten degree body rotation. Maintain a narrow, balanced standing position with both legs naturally extended and approximately five to eight centimetres of visible space between the feet. One foot is placed slightly forward by about five centimetres, creating subtle depth without crossing the body's vertical centreline. Both knees remain naturally straight and relaxed. Keep the thighs, knees, calves and ankles clearly distinguishable, with clear separation between the two legs. Both feet point naturally forward with a slight outward angle, weight balanced. Head facing the camera almost square-on, chin level, eyes to the lens or just beside it. Natural stance: the two legs clearly separated and individually readable from hip to ankle, both feet fully visible and grounded, knees relaxed rather than locked or deeply bent.
```
