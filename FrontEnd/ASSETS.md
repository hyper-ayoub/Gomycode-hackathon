# Visual assets

## Logo

Source: user-provided `C:/Users/pc/Documents/logo.html`. The original gradient, organic outline and cross are implemented in `src/components/Logo.tsx` and `public/favicon.svg`. The animated variant preserves the source morphing idea with CSS and a static fallback. The original file is unchanged.

## Current landing hero

The landing hero uses the illustration URL provided by the user:

https://img.magnific.com/photos-premium/illustration-medicale-conceptuelle-isolee-creee-ia-generative_115122-96209.jpg

It is referenced directly in `src/features/LandingPage.tsx` with French/Darija alternative text. Availability depends on the external image host.

## Previous family hero image (unused)

Saved at `public/images/darijadoc-family.png`. Created using the built-in image generation tool, not the CLI. This is illustrative fictional imagery, not a real patient testimonial. Retained as an unused asset after the user requested the replacement above.

Final prompt:

> Use case: photorealistic-natural. Asset type: editorial hero photograph for DarijaDoc, a Moroccan health literacy website. Create a beautifully composed natural documentary-style landscape photograph, 1536x1024. A Moroccan woman aged about 30 with curly dark hair in a pale blue cotton shirt sits beside her mother aged around 60 in a simple muted green blouse in a bright contemporary Moroccan home. They look together at a smartphone held by the daughter, with a plain medical paper on the table. Warm attentive expressions, quietly relieved, NOT grinning at camera. True-to-life skin and hands, casual candid moment, a reassuring family connection. Cream white plaster walls, soft sunlit window, small restrained green plant, barely visible traditional geometric tile detail. Colors primarily white, natural skin, soft green #E6F4EC, pale blue #E6EFF7. Both subjects well within frame, uncluttered composition, refined editorial photography, natural 50mm lens perspective and soft depth of field. No visible readable text, no logos, no brand marks, no medical devices, no pills, no overlays, no graphics, no collage. This is illustrative fictional imagery, not a real patient testimonial.
