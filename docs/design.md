# Desktop glass appearance

LocalPhraser is a desktop dictation workspace. A taskbar window contains Home and Settings,
with history, speaking statistics and direct recovery access. Pearl/cyan/violet light behind
frosted panels separates navigation, history and readable inset controls. Thin reflective
edges, translucent gradients and fine static grain give the panels depth. The floating
capsule keeps its high opacity, no outline and no competing native frame. No animation timer
or external background image is used.

## Tokens and layout

| Role | Value |
| --- | --- |
| Light glass | Pearl `#f5f9ff` through ice blue `#e1edf9` |
| Light text | `#163c42` |
| Dark glass | Midnight `#151b31` through slate `#242a41` |
| Dark text | `#edf8f7` |
| Ambient light | Cyan `#4a9fe7`, violet `#9976de`, teal `#3ab7c7` |
| Primary action | Blue/violet gradient; darker backing maintains white-label contrast |
| Focus | Light `#365f95`; Dark `#9fd9ff`, visible 2 px border |
| Typography | Installed Segoe UI; 28 px product title, 13–14 px labels and preview |

The taskbar workspace has a left navigation rail, saved-word/dictation/pace summaries,
and a history list beside an original/result detail pane. Settings retains a left-aligned
scrolling form and a fixed Save/Cancel row. Successful Save returns to Home; a missing selected
speech model downloads before saving, with progress/cancellation and no configuration switch
on failure. Edits made during a download require a fresh Save. Theme selection applies
and saves immediately without applying other edited fields. The draggable
header and accessible Close button replace the native caption. A size grip supports resizing;
the existing Escape and keyboard navigation behavior remains. Latest transcript keeps Result
and Raw tabs. The click-through dictation capsule shows Listening and recent words only.

```text
Settings / Latest                Dictation capsule
┌ draggable title       Close ┐   ╭───────────────────────╮
│ primary content            │   │ ● Listening           │
│ scrollable controls        │   │ recent spoken words   │
│                            │   ╰───────────────────────╯
│              Save   Cancel │
└────────────────────────────┘
```

## Implementation and accessibility

`appearance.py` paints diffused color behind translucent panels, a fine rim and upper
reflection with Qt. A cached, static 64 px grain texture breaks gradient banding; it does
not animate or repeatedly sample the desktop. Embedded Settings uses the parent material
instead of painting another opaque canvas. The transcript pane and list are distinct glass
layers, with an unpainted splitter gap and clean tabs rather than native boxed edges.
The main/recovery windows on Windows 11 build 22621+ can accept a DWM desktop acrylic
backdrop request; older systems,
offscreen tests and rejected native requests use an opaque painted fallback. Composition
policy can still reduce effects even when the API accepts a request. High contrast removes
the custom control sheet and uses the system palette with an opaque surface.

Appearance follows System by default; Light and Dark overrides are saved locally. Changing
only appearance preserves the loaded pipeline and Latest transcript. Open surfaces follow
the application palette, including stylesheet-controlled widgets. Palette notifications are
deduplicated to avoid recursive restyling. The capsule retains its no-focus and click-through
window flags, and uses plain text rather than interpreting recognized markup. It uses a
single alpha-painted surface and requests no DWM backdrop or outline, avoiding the native
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
