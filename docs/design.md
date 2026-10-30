# Desktop glass appearance

LocalPhraser is a quiet dictation utility. Its distinctive surface is a frosted, rounded
dictation capsule; Settings and Latest transcript use the same glass material with readable
inset controls. Motion is unnecessary: the design adds no animation timer or graphics assets.

## Tokens and layout

| Role | Value |
| --- | --- |
| Light glass | White through pale mint `#dcefed` |
| Light text | `#163c42` |
| Dark glass | Slate `#2b393c` through `#132228` |
| Dark text | `#edf8f7` |
| Primary action / focus | Teal `#226e69` / `#287e79` |
| Typography | Installed Segoe UI; 28 px product title, 13–14 px labels and preview |

Settings retains a left-aligned scrolling form and a fixed Save/Cancel row. The draggable
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

`appearance.py` paints a tinted gradient, fine rim and subtle upper reflection with Qt.
Windows 11 build 22621+ can accept a DWM desktop acrylic backdrop request; older systems,
offscreen tests and rejected native requests use an opaque painted fallback. Composition
policy can still reduce effects even when the API accepts a request. High contrast removes
the custom control sheet and uses the system palette with an opaque surface.

Appearance follows System by default; Light and Dark overrides are saved locally. Changing
only appearance preserves the loaded pipeline and Latest transcript. Open surfaces follow
the application palette, including stylesheet-controlled widgets. Palette notifications are
deduplicated to avoid recursive restyling. The capsule retains its no-focus and click-through
window flags, and uses plain text rather than interpreting recognized markup.

The native appearance check saves owned-window screenshots and verifies live theme changes,
focus safety, compact-window Save visibility and Close behavior. These checks complement
manual checks with Windows scaling, high contrast, transparency settings and multiple monitors.

Design guidance: [frontend-design skill](https://github.com/anthropics/skills/tree/main/skills/frontend-design).
Platform references: [Qt color schemes](https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop),
[DWM backdrop types](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type),
[DWM client frame](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmextendframeintoclientarea).
