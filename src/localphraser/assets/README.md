# Generated transcription mark

`logo.png` was created with the built-in image generation tool on 2026-11-02 at the user's
explicit request for a simpler black/white/gray taskbar icon. It replaces the earlier blue
glass mark. It is the shared source for the sidebar, window/tray icons and packaged Windows
icon. The generated alpha channel is retained. Runtime Qt scales it for each icon size;
`python scripts/build_icon.py` regenerates the multi-size `packaging/localphraser.ico`.
No external image service is contacted by the application.

Final generation prompt:

> Design exactly ONE finished app icon for LocalPhraser, an offline speech-to-text Windows
> app. Monochrome only: pure white symbol on a near-black charcoal rounded-square tile,
> with at most one subtle medium-gray edge. Extremely simple, flat, crisp, bold, futuristic
> geometric identity. The symbol combines three thick vertical audio bars of unequal heights
> on the left with two short thick horizontal transcription strokes on the right, integrated
> into one balanced compact emblem with generous negative space. It must be instantly readable
> at 16x16 and 24x24 taskbar size. Strong simple silhouette, uniform thick strokes, no tiny
> details. Front facing, perfectly square, centered, tile occupies 88 percent of canvas with
> transparent padding outside rounded corners. Genuine transparent alpha outside tile.
> Opaque black tile interior and solid opaque white symbol. NO blue, NO colors, NO glow,
> NO reflections, NO texture, NO intricate glass shapes, NO gradients, NO 3D perspective,
> NO microphone, NO speech bubble outline, NO text or letters, NO watermark, NO surrounding
> shadows, NO mockup or presentation sheet. Think precision minimalist operating-system app
> icon with an understated science-fiction feel.

## Exact color swap — 2026-11-02

The user requested the exact same design with a white tile and black symbol. Two built-in
image-edit attempts added edge/alpha artifacts and were rejected. The user explicitly chose
an exact pixel inversion instead. Qt inverted RGB only; all 1,572,516 alpha values and the
1254 by 1254 dimensions were verified unchanged, and every RGB channel was verified equal
to 255 minus its original value after saving/reloading the PNG. The source PNG SHA-256 before
inversion was `f8b47abae6f296a6a445b1653dd78a291a98b3968d7d339ff9e05fedee090038`.
The multi-resolution ICO was regenerated from this final PNG.

The rejected image-edit prompt requested a strict black/white swap, preserving every
silhouette, stroke width, bar length, placement, corner radius, spacing, canvas size and
transparency. Neither generated edit is bundled with the application.
