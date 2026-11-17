# Recognition accuracy: quiet, paused speech and a second speech engine

Status: approved by the user on 2026-11-16. Date: 2026-11-16.

## Why

The user reports that dictation "seems to miss a few words, and often mistranscribes words",
and that it gets worse "when I talk quieter and don't distinguish from word to word and add
more time in between each word". Recognition accuracy is the first priority of a wider
request to improve the app. UI and insertion across apps are later, separate pieces of work.

## What was measured

All measurements use Windows SAPI synthetic speech (no microphone, no user transcripts):
six fixed sentences, 88 words, spoken normally and with a 700 ms pause between words, scaled
to three levels over white room noise (RMS 0.002), with a key-press click added near the
start and end. A synthetic voice articulates clearly, so these numbers show the effect of
volume and pauses. They do not show the effect of words run together. Each cell is 88 words,
so a difference of one or two points is one or two words and is not meaningful.

Errors per 100 words (word error rate), continuous / paused. Above 100 means invented text.

| Engine and settings | Normal (peak 0.25) | Quiet (peak 0.02) | Very quiet (peak 0.008) | Noise only: words invented |
| --- | --- | --- | --- | --- |
| `base.en`, as shipped (Accurate) | 0.0 / 2.3 | 2.3 / 4.5 | 54.5 / 100.0 | 0 |
| `base.en`, level corrected | 0.0 / 2.3 | 3.4 / 2.3 | 33.0 / 118.2 | 0 |
| `base.en`, level corrected, repeats dropped | 0.0 / 2.3 | 3.4 / 2.3 | 33.0 / 100.0 | 0 |
| `base.en`, level corrected, repeats dropped, temperature retry | 0.0 / 2.3 | 3.4 / 2.3 | 33.0 / 89.8 | 0 |
| `small.en`, as shipped (Accurate) | 0.0 / 2.3 | 1.1 / 8.0 | 30.7 / 55.7 | 0 |
| `small.en`, level corrected, repeats dropped, temperature retry | 0.0 / 1.1 | 1.1 / 4.5 | 13.6 / 33.0 | 0 |
| Parakeet TDT 0.6b v2, int8, no filter | 0.0 / 0.0 | 1.1 / 2.3 | 15.9 / 22.7 | 0 |

Time to recognise one 10-second clip on this machine (Ryzen 5 8640HS, 6 cores, busy with
other work, so compare the rows with each other and not with a quiet machine):

| Engine | 6 threads | 16 threads (the user's current setting) |
| --- | --- | --- |
| `base.en`, Accurate | 1.1 s | 7.0 s |
| `small.en`, Accurate | 4.6 s | 46.7 s |
| `medium.en`, Fast | 6.6 s | not run |
| Parakeet TDT 0.6b v2 | 0.6 s | not run |

Parakeet on long clips: 34 s clip in 2.8 s, 63 s in 6.1 s, 132 s in 14.0 s, no word errors;
process memory 0.7 GB after loading and 2.1 GB at peak on the 132 s clip. Loading takes 5.7 s
with the file already in the disk cache.

What this shows:

1. Whisper with its speech filter loses very quiet speech, and `base.en` loses all of it
   when the words are also separated by pauses. Correcting the level roughly halves the loss
   on both Whisper models. On `base.en` with paused speech it makes the model repeat itself,
   which is worse than silence unless the repeats are dropped.
2. The user's profile asks for 16 threads on 6 cores, which makes recognition 3 to 10 times
   slower. Nothing in the app prevents this.
3. Parakeet is faster than `base.en`, needs no speech filter, and keeps most of the very
   quiet, paused speech that Whisper drops. With the level fix, `small.en` matches it on very
   quiet continuous speech, stays behind on paused speech, and takes about five times as long.
   NVIDIA reports 6.05% average word error rate for it on the public Open ASR test sets.

Not measured: whether the last word is cut when the key is released (argued from the code:
capture stops in the same call that handles the release), and real human speech.

## Goals

- Quiet speech with pauses between words is recognised nearly as well as normal speech.
- Fewer wrong words in ordinary dictation, through a more accurate engine.
- Recognition is never slowed down by a thread setting.
- The last word is not clipped on release.
- The user is told when the microphone level is the problem.
- A committed, repeatable benchmark shows all of the above without a microphone.

## What counts as done

- Judged with the default engine on the committed benchmark, at the Quiet level (peak 0.02)
  and at peak 0.014, continuous and paused: at most 5 errors per 100 words. Normal level:
  no worse than `base.en` as shipped.
- Speech below the notice threshold (1.3) is not promised. There the user gets the notice.
- No shipped engine or setting invents words on any noise-only clip, at any level in the
  benchmark, including Whisper with level correction. A setting that fails this is not
  shipped; the builder reports it.
- If Parakeet's long-recording memory limit (2.1) is not met with 30 s pieces, try 20 s
  pieces. If it is still not met, stop and report the measured numbers before going on.

## Non-goals

- UI redesign, Settings restructuring, insertion across more apps.
- GPU inference, larger Whisper models, languages other than English.
- Changing how polishing works.

## Anti-goals

- Inserting text that was not said. Every noise-only clip in the benchmark must produce no
  words with every engine and setting that ships.
- A change that makes normal-volume dictation less accurate or noticeably slower.
- Touching `dist/LocalPhraser` or the user's profile before the user approves a switch.
- Capturing the user's microphone or reading their transcripts in tests.

## Constraints

- `AGENTS.md`: development builds under `.cache/development-build`, launched only with
  `--config` set to the absolute path of `.cache/development-profile/config.json`; separate
  settings, history, vocabulary, locks and model downloads; synthetic fixtures only.
- The app stays offline at run time. Models are downloaded only by the explicit installer,
  pinned to a revision and verified by SHA-256, as `models.install_artifacts` does today.
- Captured audio buffers are zeroed after use; new copies must be zeroed the same way.
- Evidence goes into `docs/testing.md` and `docs/roadmap.md` in the existing style.

## Approaches

- **A. Fix what surrounds the Whisper model.** Level correction, repeat guard, thread cap,
  tail capture, quiet-input notice, `small.en` as default. Small and contained. Measured
  ceiling: very quiet speech still loses a third to all of its words.
- **B. A, plus Parakeet as a second engine.** Larger change: new recogniser, a 661 MB model,
  a new dependency (`onnx-asr`, MIT), a CC-BY-4.0 model notice, and vocabulary hints do not
  apply to it. Measured: best accuracy and best speed of everything tried.
- **C. A, plus a larger Whisper model.** `medium.en` needs 6.6 s for a 10-second clip on its
  fastest setting. Dropped as too slow for hold-to-talk on this CPU.

The user chose "A, then trial B". The trial is done and its numbers are above. This design
therefore covers B: the engine-independent parts of A, a small Whisper fix, and Parakeet as
the recommended engine. Part 2 can be cut without affecting Part 1.

## Part 1: fixes that apply to every engine

### 1.1 Thread count

- `cpu_threads` gains the value `0`, meaning Automatic, and `0` becomes the default.
- The count actually used is `min(setting or physical cores, physical cores, 8)`, at least 1.
  Physical cores come from `psutil.cpu_count(logical=False)`, with half of `os.cpu_count()`
  as the fallback. One function computes it; the Whisper recogniser, the Parakeet recogniser
  and the polishing model all use it.
- A saved value above the cap still loads (validation stays `0..16`) and is capped when used.
  The file is not rewritten. This is what fixes the user's 16 on a switch.
- Settings shows "Automatic" for 0 and limits the spin box to the cap.

### 1.2 Tail capture

- After release, capture continues for 250 ms and then stops. The key's own click lands in
  that tail; engines are measured with a click present.
- The indicator changes to "Transcribing" at once on release. The tail must not feel like lag.
- The tail is skipped when the recording buffer is full. A cancel, a shutdown or a new
  generation during the tail must leave no recording running and insert nothing.
- The "No speech captured" check runs on the audio including the tail.
- The 250 ms is one named constant. The pipeline stays independent of Qt, so the delay
  mechanism is injectable for tests.

### 1.3 Quiet-input notice

- A level is computed for each recording: split into 20 ms frames, take each frame's peak,
  drop the three loudest frames (key clicks), use the loudest remaining frame.
- When that level is below 0.012 (between the benchmark's Quiet and Very quiet), the result
  notice gains: "Microphone input was very quiet. Raise the input level in Windows Sound
  settings or move closer." When nothing was recognised, the message replaces "No speech
  recognized." The tray shows it at most once per app session; Latest transcript always
  shows it.

### 1.4 Whisper: level correction and repeat guard

- Before decoding, audio whose level (as in 1.3) is below 0.3 is multiplied so the level
  reaches 0.3, by at most 40 times, then clipped to ±1. Louder audio is left untouched.
  This applies to the final decode and to live preview. The boosted copy is zeroed after use.
- Segments with a compression ratio above 2.4 are dropped. This is Whisper's own measure of
  a repetition loop.
- The speech filter stays on with its current settings. A lower threshold (0.35) and a
  second pass without the filter were measured and changed nothing, so they are not built.
- Temperature retry (0, then 0.2, then 0.4 when a segment fails Whisper's own checks) was
  only measured together with the two changes above. It recovered ten words on the worst
  `base.en` case and cost 7.6 s per failing clip. The committed benchmark measures it
  separately on `base.en` and `small.en`. It ships only if it lowers errors on very quiet
  speech for `small.en`, invents nothing on noise-only clips, and adds no time at normal
  and quiet levels. Otherwise it is left out.

### 1.5 Benchmark

- `scripts/benchmark_quiet_speech.py`: the clips described under "What was measured", every
  installed speech model selected on the command line, word error rate per condition, words
  invented on noise-only clips, and time per clip. It follows
  `scripts/benchmark_recognition_quality.py` and reuses `diagnostics.synthetic_audio`'s way
  of producing speech. It adds two levels between Quiet and Very quiet (peaks 0.014 and
  0.011) so the point where an engine starts failing is visible, and one 128 s clip.
- Results are recorded in `docs/testing.md`, with the machine and its load noted.

## Part 2: Parakeet as a second engine

### 2.1 Engine

- New recogniser class beside `WhisperRecognizer`, implementing the same `Recognizer`
  protocol plus `warm_preview`, `preview` and `preview_ready`. It loads the int8 ONNX files
  from a local directory through `onnx-asr` with ONNX Runtime's CPU provider and the thread
  count from 1.1. It never passes a model name that could trigger a download.
- No speech filter and no level correction: neither improved its results.
- Recordings longer than 30 s are decoded in pieces, cut at the quietest 200 ms between
  20 s and 30 s of each piece, and the texts joined with a space. This bounds memory. The
  128 s benchmark clip must show no added errors at the cuts and peak memory under 1.3 GB.
- The existing audio guards stay: the same minimum length and "No speech captured" checks.
- Partial results: the recogniser reports each piece as it completes. Live preview decodes
  the last six seconds, as today.

### 2.2 Catalog, install and defaults

- `MODELS` gains `parakeet-tdt-0.6b-v2`. Its files are `config.json`, `vocab.txt`,
  `nemo128.onnx`, `decoder_joint-model.int8.onnx` and `encoder-model.int8.onnx` from
  `istupakov/parakeet-tdt-0.6b-v2-onnx`, installed and verified by the existing installer.
- The pipeline factory picks the recogniser class from the model name.
- `diagnostics.py` and `scripts/benchmark_recognition_quality.py` construct
  `WhisperRecognizer` directly today. They use the same factory.
- It is the default model for new profiles and the default of the `install-model` and
  `verify-model` commands. First-launch setup therefore downloads Parakeet (~660 MB) where
  it downloads `base.en` (~145 MB) today, with the existing byte progress. The first-launch
  text, `packaging/START_HERE.txt`, `docs/release-checklist.md` and their tests state the
  new name and size. Its hint reads: "Recommended (~660 MB). Most accurate and fastest
  in this app's benchmark. English only." Existing profiles keep their model.
- The recogniser is loaded in the background at app start when Parakeet is selected, using
  the existing "Preparing speech model" state, because loading takes several seconds.
- "Recognition quality" has no effect on Parakeet. Settings disables it while Parakeet is
  selected and says so in its hint.

### 2.3 Vocabulary

- Parakeet cannot take vocabulary hints. With Parakeet, approved vocabulary terms restore
  spelling instead: when consecutive recognised words, compared without case, spaces or
  hyphens, equal an approved term, they are replaced by the term as approved ("local
  phraser" becomes "LocalPhraser", "pyside" becomes "PySide"). Punctuation attached to the
  words is kept. Nothing is replaced on a sound-alike or partial match.
- The raw transcript shown in Latest transcript is the text after this step.
- The Vocabulary page explains which behaviour the selected engine uses. Whisper keeps hints.

### 2.4 Packaging and notices

- `onnx-asr` 0.12.0 (the version trialled) is pinned in `pyproject.toml` and
  `requirements-dev.lock`; `onnxruntime` becomes a direct dependency at the version already
  locked. The PyInstaller spec collects `onnx_asr`.
- `THIRD_PARTY_NOTICES.md` and `docs/bundled-dependencies.md` gain `onnx-asr` (MIT) and the
  Parakeet model (CC-BY-4.0, NVIDIA; ONNX conversion by istupakov). The model is downloaded
  by the user, not bundled.
- `docs/model-options-and-latency.md`, `docs/architecture.md`, `docs/privacy.md` and the
  README are updated where they say recognition is Whisper only.

## Tests

- Model-free unit tests for: thread resolution; config accepting 0 and 16; the level
  measure ignoring a click; boost only, capped, clipped, zeroed; repeat guard; tail capture
  including cancel, full buffer and shutdown during the tail; quiet notice; recogniser
  choice by model name; Parakeet long-clip cutting with a fake model; vocabulary spelling
  restore; installer file list for Parakeet.
- An opt-in real-engine test for Parakeet like the existing Whisper one: network denied,
  silence produces no text.
- The existing 430 tests keep passing. Ruff and mypy stay clean.

## Verification before proposing a switch

1. Full test suite, Ruff, mypy.
2. Benchmark with `base.en`, `small.en` and Parakeet from the development model directory;
   numbers recorded in `docs/testing.md`.
3. Development build under `.cache/development-build`, started with the development profile,
   Parakeet installed into the development model directory. Offscreen and background checks
   only while the user is working.
4. The user tries the development build with their own voice (Ctrl+Shift+F11, read the
   result in Latest transcript). This is the only check with real speech.
5. Only then: propose replacing the stable build, keeping its launcher path, and selecting
   Parakeet and Automatic threads in the user's profile.

## Left to the builder

- Module layout for the new recogniser and the shared level function.
- The delay mechanism for the tail, and how the pipeline exposes it to tests.
- Exact wording of hints and notices beyond the sentences quoted here.
- Whether the benchmark shares code with the existing quality benchmark.

## Calls made by the author, not decided by the user

- 250 ms tail; the thread cap of 8; the notice threshold 0.012; boost target 0.3 and cap 40.
- The pass mark under "What counts as done", and what happens when a limit is missed.
- Parakeet as the default for new profiles, which makes the first-launch download ~660 MB.
- Spelling restore as the vocabulary behaviour for Parakeet.
- Loading Parakeet at app start.
- Cutting long Parakeet recordings into pieces of at most 30 s.

## Appendix: how the trial clips were made

The committed benchmark reproduces these exactly, so the tables above stay a baseline. The
trial scripts and their logs are kept, uncommitted, in `.cache/parakeet-trial/scripts`
(`quiet_bench.py` for speech and noise, `bench2.py` for the click, level function and
Whisper variants, `parakeet_bench.py` and `parakeet_long.py` for Parakeet).

- Sentences, 88 words in total:
  1. I think we should move the meeting to Thursday afternoon because several people are away
  2. Please remind me to call the dentist tomorrow morning before I leave for work
  3. The new version fixes the problem where the window would not open after a restart
  4. Can you send me the notes from yesterday so I can read them on the train
  5. We need to order more paper and a new keyboard for the front desk
  6. It was not the first time the delivery arrived late and nobody told us
- Voice: the default SAPI voice, written to a WAV file and resampled to 16 kHz mono.
- Continuous: `voice.Speak(text)`.
- Paused: one SAPI XML utterance, `<rate speed="-3">` around the words joined by
  ` <silence msec="700"/> `, spoken with flag 8 (XML). The words are not synthesised apart.
- Level: the clip is scaled so its peak is 0.25, 0.02 or 0.008, then padded with 0.5 s of
  silence on each side, then white noise of RMS 0.002 is added over the whole clip
  (`numpy.random.default_rng(i)`, `i` the sentence index from 0).
- Click: an 8 ms burst of white noise with an exponential decay (time constant 2 ms), peak
  0.35, generator seed `1000 + i`, added 50 ms after the start and 120 ms before the end.
- Noise-only clips: white noise from `default_rng(7)`, drawn in this order: RMS 0.002 for
  3 s, 0.002 for 8 s, 0.0005 for 5 s, 0.006 for 5 s; each with the click, seeds 1000 to 1003.
- Scoring: lower-case, keep runs of letters and apostrophes, word-level edit distance over
  the reference word count, summed across the six sentences.
- Whisper rows: beam 5, English, no conditioning on previous text, without timestamps,
  6 threads, int8. Parakeet rows: `onnx-asr` 0.12.0, int8, CPU provider, 6 threads.
- The 10-second timing clip is sentences 1 and 2 spoken as one continuous utterance at
  peak 0.25. The long clips repeat the six sentences at peak 0.25 with 1 s gaps.
