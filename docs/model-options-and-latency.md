# English model options and delivery latency

The catalog retains Tiny, Base and Small and adds:

| Model | Approximate download | Purpose |
| --- | ---: | --- |
| `distil-small.en` | 335 MB | English distilled decoder; a lower-latency option to try |
| `distil-medium.en` | 790 MB | A larger distilled English model; higher CPU/memory cost |
| `medium.en` | 1.53 GB | Full Medium English model; expect more processing time |

Sources checked 2026-10-30: publisher catalogs for
[Distilled Small](https://huggingface.co/Systran/faster-distil-whisper-small.en),
[Distilled Medium](https://huggingface.co/Systran/faster-distil-whisper-medium.en) and
[Medium](https://huggingface.co/Systran/faster-whisper-medium.en).
These are CTranslate2 conversions from the existing speech-model publisher, rather than
new inference backends. Distilled models use `vocabulary.json`; original Whisper conversions
use `vocabulary.txt`. The installer pins a repository revision, verifies upstream LFS hashes,
and verifies every catalog artifact again locally. No repository Python code is executed.
Models download only through explicit selection/download; the default model is unchanged.

## Decoding change

Final recognition for clips up to 30 seconds and live drafts now request
`without_timestamps=True`, retaining greedy decoding, VAD, English, vocabulary hints and
the existing local-only CPU/int8 runtime. This avoids generating unused timestamp tokens.
Longer recordings retain timestamp-guided window advancement: a repeated synthetic-speech
fixture reproduced unwanted repetition when timestamps were disabled across a long clip.
The optimization is therefore bounded to the model's single-window duration.
The corrected path and the previous decoder both retained all eight repetitions in a
31.47-second generated fixture, with identical output length. Boundary tests cover 30,
31 and 90 seconds.
Final target insertion remains one complete checked dispatch after optional polishing.

On this development machine, a fixed 14.32-second Windows SAPI fixture with three alternating
runs per condition, Small English, int8 and four CPU threads produced:

| Timestamp generation | Decode seconds | Median |
| --- | --- | ---: |
| Enabled (previous behavior) | 3.414, 3.141, 3.001 | 3.141 |
| Disabled | 2.592, 2.851, 2.904 | 2.851 |

The recognized text was identical across all six runs. This is about 9% lower median
decoding time for this fixture, not a promise of 9% lower end-to-end latency or a speech
accuracy benchmark. It excludes polishing, target verification and application rendering.
The first sample includes first-use inference effects. The fixture contained only generated,
nonsensitive speech and was removed after the check; the report contains timing metadata only.

Raw mode avoids the polishing pass. Polished mode still waits for a complete, word-preserving
edit before insertion. The new selector explains that larger models may cost more time;
users can compare models on their own speech without an automatic quality-changing migration.

All three added models passed the existing synthetic-speech check with Python socket
connections denied, both cold and warm. Catalog/hash regression tests, keyboard popup
selection and catalog tests passed. These checks do not measure recognition
accuracy on real accents, noise or microphones.

## Readable glass

Settings popups use solid theme-specific backgrounds, spaced selectable rows, keyboard
navigation and a visible chevron. The dictation capsule keeps its transparent rounded corners
but uses a 250/255 surface alpha, so underlying text no longer competes with the preview.
The shared [generated transcription mark](../src/localphraser/assets/README.md) supplies
runtime icons and the checked-in multi-size Windows ICO. Regenerate the ICO with
`python scripts/build_icon.py`.
Native menu-opening checks wait for Windows' combo animation before capturing the popup.
