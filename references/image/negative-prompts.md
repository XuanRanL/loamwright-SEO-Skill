# Image Negative Prompts (by category)

> Used as `negative_prompt` field in image generation. Appended to every prompt.

## Universal negatives (apply to ALL images)
- no text overlays, no watermarks, no captions on image
- no AI face tells: extra fingers, asymmetric eyes, melted teeth, wrong proportions
- no inconsistent lighting or shadows
- no overly saturated colors, no HDR over-processing
- no stock photography clichés (corporate handshake, generic smile-at-camera)
- no logos other than subject's natural gear
- no chatbot reference markup (citeturn, oai_citation)
- no utm_source= parameters in any visible URL

## Photo-style negatives (when style = editorial/product/documentary)
- no cartoon, no illustration, no painted style, no 3D render look
- no low resolution, no JPEG compression artifacts
- no obvious AI compositing seams

## Illustration-style negatives (when style = flat/isometric/infographic)
- no photorealistic lighting, no realistic shadows
- no photographic noise / film grain
- no busy scenes; keep clean and clear

## Product photography negatives
- no busy backgrounds
- no distracting reflections
- no human models unless explicitly required
- no logo conflicts (other brands)

## Lifestyle photography negatives
- no obviously posed subjects looking at camera
- no studio backdrops
- no perfect/sterile environments

## Documentary/case-study negatives
- no over-staged scenes
- no fake-natural lighting
- subjects should look unaware of camera

## Conceptual photography negatives
- no literal interpretation of metaphor
- no clip-art symbolism (e.g., literal lightbulbs for ideas)
- avoid clichés (e.g., chess pieces for strategy, mountain summit for success)

## Anti-AI-fingerprint negatives (always apply)
- no Midjourney aesthetic (over-stylized, color-saturated)
- no DALL-E 2 cartoon-painterly blend
- no over-symmetric compositions
- no exaggerated bokeh

## Anti-watermark
- no Shutterstock watermark
- no Getty Images watermark
- no Adobe Stock watermark
- no stock-photo border or labels

## Cannabis / horticulture LED grow light (industry-specific)

> Trigger: when `brand-config.industry` matches `cannabis-lighting`, `horticulture-lighting`,
> `grow-light`, or `controlled-environment-agriculture`.

### Competitor brand exclusions (CRITICAL — never appear in generated images)
- no Fluence logo, no "Fluence" wordmark, no Fluence SPYDR or RAPTR fixtures
- no Gavita logo, no Gavita Pro 1700e / 1930e / RS fixtures
- no Mars Hydro logo, no FC-E / FC-8000 / TS-series fixtures
- no Spider Farmer logo, no SE / SF / G-series fixtures
- no Photontek / PHOTONTEK logo, no XT CO2 PRO fixtures
- no ChilLED Tech logo, no Growcraft fixtures
- no HLG / Horticulture Lighting Group logo, no Quantum Board branding
- no California LightWorks logo, no MegaDrive
- no Growers Choice logo, no ROI-E720 / ROI-E420 fixtures
- no Black Dog LED logo, no PhytoMAX
- no BIOS Lighting logo, no Icarus
- no TSRgrow logo
- no AC Infinity logo on grow light fixtures
- no Scotts Miracle-Gro / Hawthorne / Signify corporate marks

### YMYL / regulatory exclusions (legal risk)
- no dried cannabis bud / nug close-ups
- no joints, blunts, pre-rolls, or smoking imagery
- no cannabis oil / tincture / extract bottles
- no edible products (gummies, chocolates, infused snacks)
- no dispensary retail interiors with product displays
- no pipes, bongs, vaporizers, or consumption devices
- no dollar bills or cash next to plants (drug-trade connotation)
- no scales weighing plant material
- no harvest scenes showing buds being trimmed in macro detail
- no medical cross / pharmacy symbols
- no needles, syringes, or pharmaceutical imagery

### Privacy / talent release exclusions
- no recognizable real human faces in close-up (hands, gloves, equipment OK)
- no identifiable tattoos
- no readable name badges or ID cards
- no children at any stage
- no recognizable license plates or street signs

### Visual cliché exclusions
- no leaf-overlay-on-everything (the 7-pointed leaf as decorative element)
- no green hue cast over entire image (looks amateur)
- no purple-only lighting (some growers actually use this but it's a cliché)
- no "futuristic neon laboratory" sci-fi look
- no NASA / Mars colonization imagery
- no white lab coats unless context is genuine research facility

### Preferred imagery (positive prompts to anchor)
- ✓ wide shots of cultivation rooms with fixtures in context
- ✓ leafy green plants (mature vegetative stage) NOT flowering buds
- ✓ technicians from behind / hands-only / equipment-focused angles
- ✓ industrial / commercial facility aesthetics (not home grows)
- ✓ controlled climate, racks, ducting, sensors, controllers
- ✓ vertical farming with leafy greens (NOT cannabis) is the safest visual

## Validated high-frequency negatives (2026-06-10, from gpt-image-2 community corpus)

Add to EVERY photo prompt's negative baseline (any style):

> AI-generated look, plastic skin, oversmoothed textures, cheap e-commerce look,
> overexposed highlights, washed-out tones, distorted grid structure, stock-photo pose

Rationale: these are the 6 highest-frequency failure modes across 100+ curated
gpt-image-2 commercial cases. "AI look" and "plastic/oversmoothed" are exactly the
P9 defect class the image-visual-qa agent regenerates for — cheaper to exclude
up-front than to regenerate after.
