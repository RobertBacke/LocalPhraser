# Polishing and vocabulary review — 2026-11-02

Only public repositories and project documentation were read. No other dictation app was
downloaded, cloned, installed or executed. These are design comparisons, not head-to-head
accuracy or privacy certifications. No external source code or prompts were copied.

## What LocalPhraser does today

Whisper already supplies some punctuation and capitals. Optional local Qwen 0.5B/1.5B Q4
polishing runs afterwards, with deterministic sampling, a deadline and an original-text
fallback. The lexical guard permits case/punctuation changes and removal of a small set of
hesitation sounds. It rejects other substitutions, insertions, reordered words, changed
numbers and negations. Names such as Codex cannot silently become another word. Conversely,
the guard also rejects a model's attempt to repair a misheard ordinary word such as last/less.
Custom instructions do not bypass the guard. Inputs over 3,000 characters fall back to Raw.

The current default prompt/model were retained. In five fixed nonsensitive cases, the
installed 1.5B model returned changed output accepted by the guard for punctuation, fillers,
numbers, technical terms and a spoken instruction. Accepted edits are not proof of semantic
or formatting quality. An unchanged already-punctuated transcript is a valid outcome.

## Open-source reference comparison

| Project | Observed approach | Useful distinction |
| --- | --- | --- |
| [Handy](https://github.com/cjpais/Handy) | Its [post-processing documentation](https://handy.computer/docs/post-processing) exposes configurable transformations and local-compatible endpoints; [custom words](https://handy.computer/docs/advanced) use imperfect matching. | Broader grammar/rewrite tasks have a different fidelity contract from our formatting-only mode. |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | Its [prompt builder](https://github.com/OpenWhispr/openwhispr/blob/main/src/config/prompts/index.ts) distinguishes transcript payloads from instructions and appends dictionary spelling hints. | Clear input framing and a separate, editable dictionary help explain what each stage does. |
| [VoiceInk](https://github.com/Beingpax/VoiceInk) | [Prompt management](https://tryvoiceink.com/docs/prompt-management) separates cleanup templates from assistant tasks. Its [Vocabulary](https://tryvoiceink.com/docs/vocabulary) distinguishes recognition hints from exact replacements. | A vocabulary entry should not be presented as a guaranteed word substitution. |

VoiceInk's [privacy documentation](https://tryvoiceink.com/docs/privacy-and-data) describes
learning from editable app text through Accessibility. LocalPhraser keeps its current
metadata-only target verification: it does not watch external text fields for corrections.
The new Vocabulary page instead reviews recurring terms from saved LocalPhraser dictations
and corrected spellings explicitly entered on that page. Suggestions are local pattern
matches, not a second LLM pass or model retraining, and never become active without approval.

## Recognition versus polishing

The user-selected default is now Balanced final decoding (beam 3), with Fast (1) and Accurate
(5) alternatives. Live preview and silent preparation retain the fast path. A repeatable
test uses fixed Windows SAPI speech, existing Base/Small English weights and 12 keyword
occurrences across three cases. Base scored 11/12 and Small 10/12 for each of the three
search settings. All settings recognized the last/less case's four target occurrences.
This tiny, clean synthetic sample did not establish an accuracy improvement or a model
ranking. The first decode also includes initialization, so its timings are not isolated
latency comparisons. Actual voice/noise/accent trials remain necessary.

```powershell
python scripts/benchmark_recognition_quality.py --root .cache/models --temp-dir .cache/quality-bench
python scripts/benchmark_refinement.py qwen2.5-1.5b --root .cache/models --prepare-lead 5
```

Reports contain case identifiers, counts and timings; they do not contain personal speech.
More permissive rewriting, automatic exact replacements and LLM term extraction remain
separate future choices, requiring their own preservation and accuracy evaluation.
