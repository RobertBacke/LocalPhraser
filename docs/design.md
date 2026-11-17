# Desktop glass appearance ("Aurora glass")

LocalPhraser is a desktop dictation workspace. A taskbar window contains Home, Settings,
Vocabulary and Analytics, with history, speaking statistics and direct recovery access.
The look is futuristic glassmorphism: a deep (dark) or luminous (light) backdrop lit by soft
aurora glows, crisp translucent panels with a bright rim and a top highlight, one neon
accent family and strong text contrast. Fine static grain breaks gradient banding. No
external background image, image file or icon font is used.

## Tokens and layout

Every colour lives in one frozen `Theme` per appearance (`appearance.theme(dark)`); the
stylesheet and all painters read from it.

| Role | Dark | Light |
| --- | --- | --- |
| Backdrop (diagonal) | `#060913` → `#0B1024` → `#120B2A` | `#F4F7FF` → `#E9EEFF` → `#F3E9FF` |
| Aurora glows | cyan, violet, faint magenta | sky, violet, pink |
| Panel | dark tint under white 9% → 4%, white rim, top highlight | white 72% → 52%, white rim inside a faint dark hairline |
| Text / muted | `#F3F6FF` / `#A7B3D1` | `#0B1433` / `#46527A` |
| Fields | inset `rgba(8, 12, 28, 0.55)` | white 85% |
| Focus (2 px) | cyan `#22D3EE` | indigo `#4F46E5` |
| Glow / indicator | `#22D3EE` | `#0891B2` |
| Primary action | `#4F46E5` → `#7C3AED` → `#C026D3`, white text | same |
| States | recording red, busy amber, ready green (`TONES`) | same roles, darker values |
| Typography | Bundled Space Grotesk; 26 px page titles, 10 pt body, 9 pt hints | same |

Panels have radius 18; a card nested in a panel is one step brighter with radius 14;
fields and buttons use radius 12. The dark panel lays a dark tint under its glass so text
contrast does not depend on the aurora behind it. Tests paint the backdrop, panels, nested
and selected cards and require 4.5:1 for text, muted text and the destructive red on every
sampled pixel, and for white on each stop of the primary gradient.

The sidebar holds the tinted logo mark, navigation rows with painted icons (the current page
is a brighter glass pill with a 3 px accent bar), a status chip and a quiet Quit row. Home
opens with a hero card: a status orb ringed in the state colour, a state chip, a headline
that states the state in words, the shortcut hint, the primary record button and a live
microphone level meter. Below it are three stat tiles and the history: a list of separate
glass cards beside a detail card with chips, a segmented Result/Original control and the
Copy and Delete actions. In a narrow window the hero drops its meter and chip, the tiles
tighten and, below 720 px, the list sits above the detail; a short window scrolls instead
of clipping.

Settings retains a left-aligned scrolling form and a fixed Save/Cancel row; each section card
has an icon beside its title and options are switches. Successful Save returns to Home; a
missing selected speech model downloads before saving, with progress/cancellation and no
configuration switch on failure. Edits made during a download require a fresh Save. Theme
selection applies and saves immediately without applying other edited fields. The draggable
header and accessible Close glyph replace the native caption. A size grip supports resizing;
the existing Escape and keyboard navigation behavior remains. Latest transcript keeps Result
and Raw as a segmented control.

```text
Settings / Latest                Dictation capsule (dark in both themes)
┌ draggable title       Close ┐   ╭───────────────────────────╮
│ primary content            │   │ ▂▅▇▅▂  Listening          │
│ scrollable controls        │   │        recent spoken words │
│                            │   ╰───────────────────────────╯
│              Save   Cancel │    level meter while recording,
└────────────────────────────┘    state dot in other states
```

## Implementation and accessibility

`appearance.py` holds the themes, builds the one stylesheet from them and paints the glass:
`paint_backdrop` (gradient, glows, grain, rim) and `paint_panel` (fill, rim, highlight) are
used by the windows, `GlassPanel`, the history-card delegate and the tests. Check boxes
remain `QCheckBox` but are painted as switches (thumb left when off, right when on, a focus
ring); the Result/Original tabs remain a `QTabBar` painted as a segmented control, so roles
and keyboard handling are unchanged. `icons.py` draws every icon with `QPainter` paths in
one 20 px, 1.7 px-stroke style; icons are decoration and every control keeps its text and
accessible name. Icons on our own buttons are painted live in theme colours, so a theme
change needs no rebuild; `icons.icon` also provides 1x/2x `QIcon`s with separate checked
and disabled colours. Destructive actions use quiet red text and border, never a filled red.

The level meter is real input level, never an animation: `Recorder.level()` is the peak of
the latest input block (one float written in the audio callback), `Dictation.input_level()`
returns it only while recording, and `Desktop` reads it about 30 times a second while
recording and feeds the capsule and the Home hero through `levels.display_level`
(−54 dBFS → 0, −6 dBFS → 1). The timer is stopped and the meters are flattened in every
other state and on shutdown. Nothing is stored or logged. There is no decorative animation.

The main/recovery windows on Windows 11 build 22621+ can accept a DWM desktop acrylic
backdrop request; older systems, offscreen tests and rejected native requests use an opaque
painted fallback. With acrylic the painted surface stays about 93% opaque so contrast does
not depend on what is behind the window. Composition policy can still reduce effects even
when the API accepts a request. High contrast removes the custom control sheet and uses the
system palette with an opaque surface; every painted element (panels, switches, segments,
icons, meter, orb, cards, bars) falls back to native drawing or palette colours.

Appearance follows System by default; Light and Dark overrides are saved locally. Changing
only appearance preserves the loaded pipeline and Latest transcript. Open surfaces follow
the application palette, including stylesheet-controlled widgets. Palette notifications are
deduplicated to avoid recursive restyling. The capsule retains its no-focus and click-through
window flags, and uses plain text rather than interpreting recognized markup. It floats over
other apps, so it is the same dark pill in both themes: a deep, nearly opaque fill with a
1 px cyan-to-violet rim painted by Qt. It requests no DWM backdrop, avoiding the native
rectangular frame previously visible around the rounded capsule.

The native appearance check saves owned-window screenshots and verifies live theme changes,
focus safety, compact-window Save visibility and Close behavior. These checks complement
manual checks with Windows scaling, high contrast, transparency settings and multiple monitors.

## Reference comparison

On 2026-11-02, Google Images results for `glassmorphism desktop dashboard UI` were inspected
visually in the in-app browser, alongside the running LocalPhraser window. The previous
mostly opaque navy panels lacked the light transmission and layered edge treatment visible
in those references. The implementation now emphasizes these material cues while retaining
readable text and controls. The Windows compositor accepted the acrylic request on the
development machine; a native window capture was inspected over an owned synthetic backdrop.
This does not establish identical effects on all Windows configurations.

Reference explanation and examples: [Clay — glassmorphism UI](https://clay.global/blog/glassmorphism-ui).
The reference images are inspiration only; none are copied or bundled into the app.

Design guidance: [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)
and [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill). See
[review and pinned versions](design-skill-review.md). Its glassmorphism domain guidance was
useful; its generated marketing-page patterns were unsuitable for this desktop workspace
and were not adopted. The existing Qt stack remains unchanged.
Platform references: [Qt color schemes](https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop),
[DWM backdrop types](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type),
[DWM client frame](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmextendframeintoclientarea).

## Settings interaction fixes

The polishing group is parented into its layout before changing visibility. In Polished
mode the previous ordering briefly showed a detached group window during construction.
The standard Qt combo popup is retained, constrained to the owning window and intersecting
screen work area, and placed above or below its control according to available space.
Long lists scroll and long labels elide; Escape and keyboard selection retain Qt behavior.
The native roll-open effect is suppressed only while opening that popup so its unconstrained
geometry is not animated first. Compact native checks cover all Settings dropdowns and a
25-device synthetic list. No new UI library or copied external code is introduced.

## Vocabulary, analytics and typography

Vocabulary and Analytics are taskbar-workspace pages using the existing material and sidebar.
Vocabulary groups adding a word, approved recognition hints and reviewable suggestions into
three cards; local pattern analysis is labeled explicitly, and correction/dismissal memory
has an explicit deletion control. Analytics uses an application/24-hour/7-day/all-time table
with a quiet header, row hover and right-aligned counts; a delegate draws a thin accent bar
under each count, proportional to the largest in its column, while the numbers stay the
cells' text. Both keep text plain and errors fixed.

The interface, transcript panes and dictation widget use bundled Space Grotesk, a geometric
sans-serif with readable text forms. The unmodified variable font and its copyright/OFL
notice come from Google Fonts' repository and have recorded hashes in third-party notices.
Windows font fallback covers missing glyphs. Native/system dialogs keep platform behavior.

The desktop retains frameless glass but adds the resizable-frame style Windows requires for
snapping. Native hit testing exposes caption drag regions, resize edges and the maximize
button, including explicit native-button click handling. A compact sidebar and wrapped
Settings rows reduce minimum-width pressure. Actual owned-window top-edge maximize and
side snapping were inspected; this does not cover every DPI/monitor policy configuration.

### Visible font and caption correction

Windows child widgets were still using Segoe UI because Qt stylesheet font settings did
not inherit the outer window's explicit font. The scoped widget stylesheet now specifies
Space Grotesk at 10 pt for descendants, preserving larger heading selectors. Tests inspect
the transcript editors, page title, navigation and Settings controls under a Segoe UI app
default, with an actual shown-window Windows probe as well. See
[Qt stylesheet inheritance](https://doc.qt.io/qt-6/stylesheet-syntax.html#inheritance).

The sidebar retains enough width for complete labels at that font size. Caption controls
use centered drawn symbols in borderless 42 × 32 logical-pixel buttons with a hover fill
(red for Close) instead of font glyphs;
the maximize symbol changes to Restore when appropriate. Page changes reveal the existing
window without restoring its size/state. Minimized windows are unminimized while retaining
their maximized/full-screen state, and normal/snapped geometry is preserved.
