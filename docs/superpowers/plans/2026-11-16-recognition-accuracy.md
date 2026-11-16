# Recognition Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quiet, paused speech recognisable, stop settings from slowing recognition, and add Parakeet TDT 0.6b v2 as the recommended speech engine beside Whisper.

**Architecture:** Engine-independent fixes land first (thread cap, level measure, tail capture, quiet notice), then a Whisper fix, then a second recogniser class chosen by model name through one factory. A committed synthetic benchmark measures every engine and decides one open setting.

**Tech Stack:** Python 3.12, PySide6, faster-whisper 1.2.1, ONNX Runtime 1.31.1, onnx-asr 0.12.0, psutil, pytest, Ruff, mypy, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-11-16-recognition-accuracy-design.md`. Read it first; its appendix defines the benchmark clips exactly.

## Global Constraints

- Never build into, replace, stop or remove `dist/LocalPhraser`. Never read the user's profile under `%LOCALAPPDATA%\LocalPhraser`.
- Development builds go to `.cache/development-build` and start only with `--config C:/Users/robbi/Projects/LocalPhraser/.cache/development-profile/config.json`.
- Tests use synthetic audio and fakes. No microphone capture. No foreground windows while the user is working; offscreen Qt only.
- The app stays offline at run time. Model downloads happen only through `models.install_artifacts`.
- Every new copy of captured audio is zeroed in a `finally` after use.
- Python: `.venv/Scripts/python.exe`. There is no `pip` in the venv; use `uv pip ... --python .venv\Scripts\python.exe`.
- After each task: `.venv/Scripts/python.exe -m pytest -q` passes, `-m ruff check .`, `-m ruff format --check .` and `-m mypy src` are clean.
- Commit on branch `recognition-quiet-speech`. End commit messages with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.
- Do not run two benchmarks or a benchmark and the test suite at the same time: timings are compared.
- Exact values from the spec: tail 250 ms; thread cap 8; quiet threshold 0.012; boost target 0.3, boost limit 40; repeat guard compression ratio 2.4; Parakeet pieces at most 30 s, cut searched from 20 s, quiet window 200 ms; memory limit 1.3 GB; pass mark 5 errors per 100 words at peaks 0.02 and 0.014.

## Review Focus

Inputs the spec implies but does not spell out. Each has a test in the task named.

1. A recording shorter than eight 20 ms frames, or empty, reaches the level measure: it returns the plain peak (0.0 when empty) and nothing raises. (Task 2)
2. `psutil.cpu_count(logical=False)` returns `None`, as on some virtual machines: the thread count falls back to half the logical count, at least 1. (Task 1)
3. Release arrives twice during the tail (key repeat, or the full-buffer watchdog): capture stops once and one transcription is submitted. (Task 3)
4. A vocabulary term with punctuation in it (`C++`, `node.js`), and an empty vocabulary: matching is literal, never a regular expression, and empty vocabulary returns the text unchanged. (Task 7)
5. A long Parakeet recording with no quiet moment (steady noise) or of exactly 30 s: every sample is decoded exactly once and no piece exceeds 30 s. (Task 7)

---

### Task 1: Automatic, capped thread count

**Files:**
- Modify: `src/localphraser/config.py`, `src/localphraser/recognition.py`, `src/localphraser/refinement.py`, `src/localphraser/ui.py:359-362`
- Test: `tests/test_config.py`, `tests/test_recognition_offline.py`, `tests/test_refinement.py`

**Interfaces:**
- Produces: `config.thread_limit() -> int`, `config.inference_threads(setting: int) -> int`. `Config.cpu_threads` default `0`, valid `0..16`.

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py`

```python
def test_thread_limit_uses_physical_cores_capped_at_eight(monkeypatch):
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 6 if not logical else 12)
    assert config.thread_limit() == 6
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 24)
    assert config.thread_limit() == 8

def test_thread_limit_falls_back_when_physical_count_is_unknown(monkeypatch):
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: None)
    monkeypatch.setattr("os.cpu_count", lambda: 4)
    assert config.thread_limit() == 2
    monkeypatch.setattr("os.cpu_count", lambda: None)
    assert config.thread_limit() == 1

def test_inference_threads_caps_saved_values_and_resolves_automatic(monkeypatch):
    monkeypatch.setattr(config, "thread_limit", lambda: 6)
    assert [config.inference_threads(n) for n in (0, 1, 4, 6, 16)] == [6, 1, 4, 6, 6]

def test_zero_and_sixteen_threads_are_valid_and_zero_is_default():
    assert Config().cpu_threads == 0
    Config(cpu_threads=0).validate()
    Config(cpu_threads=16).validate()
```

In the existing invalid-values parametrisation replace `{"cpu_threads": 0}` with `{"cpu_threads": -1}` and add `{"cpu_threads": 17}`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`. Expected: the four new tests fail.
- [ ] **Step 3: Implement** both functions in `config.py` (`psutil` imported inside `thread_limit`), change the default and the validation message to "CPU threads must be 0–16."
- [ ] **Step 4: Use it.** `WhisperRecognizer.__init__` and `LocalRefiner.__init__` store `inference_threads(cpu_threads)`; both default the parameter to `0`. In the existing test that asserts `cpu_threads=2` reaches `WhisperModel`, patch `localphraser.config.thread_limit` to return 8. Add one test per class that a setting of 16 with a limit of 6 passes 6 to the engine.
- [ ] **Step 5: Settings.** `self.threads.setRange(0, thread_limit())`, `setSpecialValueText("Automatic")`, value `min(config.cpu_threads, thread_limit())`. Add a test in `tests/test_startup.py` style: a config with `cpu_threads=16` opens Settings showing the limit, and `cpu_threads=0` shows the text "Automatic".
- [ ] **Step 6: Run the full checks** from Global Constraints. Expected: all pass.
- [ ] **Step 7: Commit** `Cap inference threads at physical cores and add automatic`.

### Task 2: Level measure, Whisper level correction and repeat guard

**Files:**
- Create: `src/localphraser/levels.py`, `tests/test_levels.py`
- Modify: `src/localphraser/recognition.py` (`_decode`)
- Test: `tests/test_recognition_offline.py`

**Interfaces:**
- Produces: `levels.QUIET_LEVEL = 0.012`, `levels.BOOST_TARGET = 0.3`, `levels.BOOST_LIMIT = 40.0`, `levels.speech_level(audio: Audio, sample_rate: int = SAMPLE_RATE) -> float`, `levels.boost_quiet(audio: Audio, sample_rate: int = SAMPLE_RATE) -> Audio`. `WhisperRecognizer.temperatures: tuple[float, ...]`, default `(0.0,)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_levels.py`

```python
def tone(level, seconds=1.0, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

def test_level_ignores_three_loudest_frames():
    audio = tone(0.02)
    for start in (800, 4000, 9000):          # three clicks, one frame each
        audio[start : start + 100] = 0.9
    assert speech_level(audio) == pytest.approx(0.02, rel=0.05)

def test_level_of_short_or_empty_audio_is_plain_peak():
    assert speech_level(np.empty(0, dtype=np.float32)) == 0.0
    assert speech_level(tone(0.2, seconds=0.1)) == pytest.approx(0.2, rel=0.05)   # 5 frames

def test_level_uses_capture_rate_for_frame_length():
    assert speech_level(tone(0.05, rate=48000), 48000) == pytest.approx(0.05, rel=0.05)

def test_boost_raises_quiet_audio_to_target_in_a_new_array():
    audio = tone(0.02)
    boosted = boost_quiet(audio)
    assert boosted is not audio and speech_level(boosted) == pytest.approx(0.3, rel=0.05)
    assert float(np.max(np.abs(audio))) == pytest.approx(0.02, rel=0.05)

def test_boost_is_limited_clipped_and_never_attenuates():
    assert speech_level(boost_quiet(tone(0.001))) == pytest.approx(0.04, rel=0.05)   # 40x
    loud = tone(0.5)
    assert boost_quiet(loud) is loud
    clicked = tone(0.02); clicked[100:200] = 0.9
    assert float(np.max(np.abs(boost_quiet(clicked)))) == 1.0
    silent = np.zeros(16000, dtype=np.float32)
    assert boost_quiet(silent) is silent
```

- [ ] **Step 2: Run** `-m pytest tests/test_levels.py -q`. Expected: import error.
- [ ] **Step 3: Implement `levels.py`.** The level: frames of `sample_rate // 50` samples, each frame's peak, sorted; with fewer than 8 whole frames return the plain peak; otherwise the fourth-largest frame peak.
- [ ] **Step 4: Write the failing recogniser tests** in `tests/test_recognition_offline.py`

```python
def test_final_and_preview_decode_boost_quiet_audio_then_zero_the_copy():
    recognizer = WhisperRecognizer(Path("unused"))
    seen = {}
    def transcribe(audio, **kwargs):
        seen["audio"], seen["peak"] = audio, float(np.max(np.abs(audio)))
        return iter([SimpleNamespace(text="hi", compression_ratio=1.0)]), None
    recognizer._model = Mock(transcribe=transcribe)
    quiet = tone(0.01)
    assert recognizer.transcribe(quiet) == "hi"
    assert seen["peak"] == pytest.approx(0.3, rel=0.05)
    assert not seen["audio"].any() and seen["audio"] is not quiet
    assert float(np.max(np.abs(quiet))) == pytest.approx(0.01, rel=0.05)
    recognizer.preview(quiet)
    assert seen["peak"] == pytest.approx(0.3, rel=0.05)

def test_repetition_loop_segments_are_dropped():
    recognizer = WhisperRecognizer(Path("unused"))
    segments = [SimpleNamespace(text="keep this", compression_ratio=1.4),
                SimpleNamespace(text="la la la la la la", compression_ratio=2.41),
                SimpleNamespace(text="and this")]                 # no attribute: kept
    recognizer._model = Mock(transcribe=lambda *a, **k: (iter(segments), None))
    assert recognizer.transcribe(tone(0.3)) == "keep this and this"

def test_temperatures_default_to_single_zero():
    recognizer = WhisperRecognizer(Path("unused"))
    recognizer._model = Mock(transcribe=Mock(return_value=(iter([]), None)))
    recognizer.transcribe(tone(0.3))
    assert recognizer._model.transcribe.call_args.kwargs["temperature"] == 0
    recognizer.temperatures = (0.0, 0.2, 0.4)
    recognizer.transcribe(tone(0.3))
    assert recognizer._model.transcribe.call_args.kwargs["temperature"] == (0.0, 0.2, 0.4)
```

- [ ] **Step 5: Implement in `_decode`.** Boost before `transcribe`; consume the segment generator inside a `try`; zero the boosted copy in `finally` when it is not the caller's array; drop segments whose `compression_ratio` (missing means 0) is above 2.4; pass `temperature=0` for a single-value tuple, the tuple otherwise. The speech filter arguments do not change. `warm_preview` keeps its own direct call.
- [ ] **Step 6: Run the full checks.** Expected: all pass.
- [ ] **Step 7: Commit** `Correct quiet input level for Whisper and drop repetition loops`.

### Task 3: Tail capture

**Files:**
- Modify: `src/localphraser/pipeline.py`, `src/localphraser/ui.py` (`make_pipeline`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `pipeline.TAIL_SECONDS = 0.25`. `Dictation(..., tail_seconds: float = 0.0, schedule: Callable[[float, Callable[[], None]], None] | None = None)`. With `tail_seconds == 0` behaviour is exactly today's, so existing tests are untouched.

Behaviour to build:
- `release()` with a tail: only when `state == RECORDING`. Set the state to `TRANSCRIBING` at once, record `released_at`, mark the tail pending, and call `schedule(tail_seconds, callback)`. The callback, run on the owner thread, stops the recorder and continues with what `release()` does today (length and silence check, submit).
- No tail when `tail_seconds <= 0` or when the recorder has a `full` event that is set.
- The default `schedule` starts a daemon `threading.Timer` whose function hands the callback to `self._post`.
- `cancel()` also works while the tail is pending: recorder cancelled, target cleared, state `IDLE` with "Recording cancelled.". A callback that arrives after a cancel, a shutdown, or for an older generation does nothing.
- `released_at` is the moment `release()` was called, in both paths.

- [ ] **Step 1: Write the failing tests** using a fixture variant that passes `tail_seconds=0.25` and `schedule=lambda delay, callback: scheduled.append((delay, callback))`, and a `FakeRecorder` that counts `stop()` calls

```python
def test_release_keeps_capturing_for_the_tail_then_stops(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    pipeline.press(); pipeline.release()
    assert recorder.stopped == 0 and pipeline.state == State.TRANSCRIBING
    assert [delay for delay, _ in scheduled] == [0.25]
    scheduled[0][1]()
    assert recorder.stopped == 1

def test_second_release_during_tail_is_ignored(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press(); pipeline.release(); pipeline.release()
    assert len(scheduled) == 1
    scheduled[0][1](); scheduled[0][1]()
    assert recorder.stopped == 1

def test_cancel_during_tail_stops_capture_and_inserts_nothing(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press(); pipeline.release(); pipeline.cancel()
    assert recorder.cancelled == 1 and pipeline.state == State.IDLE
    scheduled[0][1]()
    assert recorder.stopped == 0

def test_shutdown_during_tail_does_not_stop_or_submit(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    pipeline.press(); pipeline.release(); pipeline.shutdown()
    scheduled[0][1]()
    assert recorder.stopped == 0

def test_full_buffer_skips_the_tail(tail_setup):
    pipeline, recorder, scheduled, _ = tail_setup
    recorder.full = threading.Event(); recorder.full.set()
    pipeline.press(); pipeline.release()
    assert scheduled == [] and recorder.stopped == 1

def test_silent_recording_after_tail_reports_no_speech(tail_setup):
    pipeline, recorder, scheduled, changes = tail_setup
    recorder.audio = np.zeros(16000, dtype=np.float32)
    pipeline.press(); pipeline.release(); scheduled[0][1]()
    assert changes[-1] == (State.IDLE, "No speech captured.")

def test_default_schedule_posts_to_the_owner_thread():
    # tail_seconds=0.01, no schedule argument; wait on the dispatch queue (timeout 2 s),
    # run the queued callback, assert recorder.stopped == 1.
```

- [ ] **Step 2: Run** `-m pytest tests/test_pipeline.py -q`. Expected: new tests fail on the unknown argument.
- [ ] **Step 3: Implement** in `pipeline.py`.
- [ ] **Step 4: Pass `tail_seconds=TAIL_SECONDS`** from `Controller.make_pipeline` in `ui.py`.
- [ ] **Step 5: Run the full checks.** Expected: all pass.
- [ ] **Step 6: Commit** `Keep capturing for 250 ms after release`.

### Task 4: Quiet-input notice

**Files:**
- Modify: `src/localphraser/pipeline.py`, `src/localphraser/ui.py` (`complete_transcript`)
- Test: `tests/test_pipeline.py`, `tests/test_home.py` or the existing UI test module that covers `complete_transcript`

**Interfaces:**
- Consumes: `levels.speech_level`, `levels.QUIET_LEVEL`.
- Produces: `pipeline.QUIET_MESSAGE = "Microphone input was very quiet. Raise the input level in Windows Sound settings or move closer."`

Behaviour to build:
- When capture stops, the pipeline measures `speech_level(audio, sample_rate)` on the captured audio and remembers whether it is below `QUIET_LEVEL`.
- Text was recognised and the input was quiet: the notice given to the `result` callback ends with a space and `QUIET_MESSAGE`. The message given to the state callback is unchanged, so the tray does not repeat it on every dictation.
- Nothing was recognised and the input was quiet: the idle state message is `QUIET_MESSAGE` where it is "No speech recognized." today. It is shown wherever that message is shown today, every time.
- `complete_transcript` shows a tray notification with `QUIET_MESSAGE` the first time a notice contains it in an app session, and not again.

- [ ] **Step 1: Write the failing tests**

```python
def test_quiet_input_adds_notice_to_result_but_not_to_state(setup):
    # recorder.audio = np.full(16000, 0.005); press, release, drain callbacks
    assert results[-1] == ("Hello, world.", f"Inserted. {QUIET_MESSAGE}")
    assert changes[-1] == (State.IDLE, "Inserted.")

def test_normal_input_adds_no_notice(setup):
    assert QUIET_MESSAGE not in results[-1][1]

def test_quiet_input_with_no_text_replaces_no_speech_message(setup):
    # recognizer returns ""; recorder.audio = np.full(16000, 0.005)
    assert changes[-1] == (State.IDLE, QUIET_MESSAGE)

def test_click_does_not_hide_quiet_input(setup):
    # audio 0.005 with a 100-sample burst of 0.9: still quiet
    assert QUIET_MESSAGE in results[-1][1]

def test_tray_shows_quiet_notice_once_per_session(desktop):
    # call complete_transcript twice with a notice containing QUIET_MESSAGE
    assert notifications.count(QUIET_MESSAGE) == 1
```

- [ ] **Step 2: Run** the two test files. Expected: new tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full checks.** Expected: all pass.
- [ ] **Step 5: Commit** `Tell the user when microphone input is very quiet`.

### Task 5: Quiet-speech benchmark

**Files:**
- Create: `scripts/benchmark_quiet_speech.py`, `tests/test_benchmark_quiet_speech.py`
- Modify: `src/localphraser/diagnostics.py` (`synthetic_audio`), `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `diagnostics.synthetic_audio(directory: Path, sample_rate: int = SAMPLE_RATE, text: str | None = None, xml: bool = False) -> Audio` (`text=None` speaks `SYNTHETIC_TEXT`; `xml=True` speaks with SAPI flag 8).
- Produces in the script: `SENTENCES`, `LEVELS = (0.25, 0.02, 0.014, 0.011, 0.008)`, `paused_markup(text: str) -> str`, `degrade(audio: Audio, peak: float, seed: int) -> Audio`, `click(audio: Audio, seed: int) -> Audio`, `noise_clips() -> list[Audio]`, `word_errors(reference: str, hypothesis: str) -> tuple[int, int]`, `check(root: Path, models: list[str], temporary: Path, *, threads: int = 0, retry: bool = False, long: bool = False) -> dict`.
- Until Task 7 the script builds `WhisperRecognizer` directly with quality "accurate". Task 7 switches it to the factory.

The clip recipe is the spec's appendix; copy the numbers from there. The reference scripts are in `.cache/parakeet-trial/scripts` (`quiet_bench.py`, `bench2.py`); the committed script must produce the same audio for the same sentence, level and seed.

- [ ] **Step 1: Write the failing model-free tests**

```python
def test_word_errors_counts_edits_over_reference_words():
    assert word_errors("the cat sat down", "The cat sat down.") == (0, 4)
    assert word_errors("the cat sat down", "the cat down") == (1, 4)
    assert word_errors("the cat", "the the the the cat") == (3, 2)

def test_paused_markup_is_one_utterance_with_700_ms_between_words():
    assert paused_markup("a b c") == (
        '<rate speed="-3">a <silence msec="700"/> b <silence msec="700"/> c</rate>')

def test_degrade_sets_peak_pads_half_a_second_and_adds_noise():
    out = degrade(np.ones(16000, dtype=np.float32), 0.02, seed=0)
    assert out.size == 32000 and out.dtype == np.float32
    assert float(np.std(out[:8000])) == pytest.approx(0.002, rel=0.1)
    assert float(np.mean(out[8000:24000])) == pytest.approx(0.02, rel=0.05)

def test_click_adds_two_bursts_of_peak_0_35_at_fixed_offsets():
    out = click(np.zeros(32000, dtype=np.float32), seed=0)
    burst = int(0.008 * 16000)
    for start in (int(0.05 * 16000), 32000 - int(0.12 * 16000)):
        assert float(np.max(np.abs(out[start : start + burst]))) == pytest.approx(0.35)
    assert not out[: int(0.05 * 16000)].any()

def test_noise_clips_are_the_four_fixed_lengths():
    assert [clip.size // 16000 for clip in noise_clips()] == [3, 8, 5, 5]

def test_sentences_total_88_words():
    assert sum(len(s.split()) for s in SENTENCES) == 88
```

Add to `tests/test_diagnostics.py` a test that `synthetic_audio(tmp, text="x", xml=True)` calls the fake SAPI voice's `Speak("x", 8)` and that the default call still speaks `SYNTHETIC_TEXT` with no flag, following how that file already fakes SAPI.

- [ ] **Step 2: Run** both test files. Expected: fail.
- [ ] **Step 3: Implement.** Output of `check`: `{"scope": ..., "threads": ..., "results": [{"model", "level", "paused", "errors_per_100", "seconds_per_clip"}], "noise_only": [{"model", "words_invented": [..4..]}], "timing_10s": [{"model", "seconds"}]}`. `retry=True` adds rows for Whisper models with `temperatures = (0.0, 0.2, 0.4)`, labelled `"<model>+retry"`. `long=True` adds `{"model", "clip_seconds": 128, "errors_per_100", "seconds", "loaded_mb", "peak_mb"}` using `psutil.Process().memory_info()` (`rss` after loading, `peak_wset` after the clip); document in `--help` that `--long` must run with one model per process. Command line: `--root`, `--models`, `--temp-dir`, `--threads`, `--retry`, `--long`. All audio arrays are zeroed after use. Nothing recognised is printed.
- [ ] **Step 4: Run the full checks**, then run the benchmark once for `base.en` from `.cache/models` with `--temp-dir .cache/quality-bench` and confirm the `base.en` rows at peaks 0.25, 0.02 and 0.008 are within 3 points of the spec's "level corrected, repeats dropped" row.
- [ ] **Step 5: Commit** `Add synthetic quiet and paused speech benchmark`.

### Task 6: Parakeet in the model catalog, installer and packaging

**Files:**
- Modify: `src/localphraser/config.py`, `src/localphraser/models.py`, `pyproject.toml`, `requirements-dev.lock`, `packaging/localphraser.spec`, `THIRD_PARTY_NOTICES.md`, `docs/bundled-dependencies.md`
- Test: `tests/test_models.py`, `tests/test_config.py`, `tests/test_bundle_inventory.py`, `tests/test_dropdowns.py`

**Interfaces:**
- Produces: `config.PARAKEET_MODEL = "parakeet-tdt-0.6b-v2"`; `MODELS` starts with it; `MODEL_HINTS[PARAKEET_MODEL] = "Recommended (~660 MB). Most accurate and fastest in this app's benchmark. English only."`. `Config.model` stays `"base.en"` in this task.
- Produces: `models.model_files(PARAKEET_MODEL) == ("config.json", "vocab.txt", "nemo128.onnx", "decoder_joint-model.int8.onnx", "encoder-model.int8.onnx")`; `install_model(PARAKEET_MODEL, root)` installs from `istupakov/parakeet-tdt-0.6b-v2-onnx`.

- [ ] **Step 1: Write the failing tests**: the file tuple above; `install_model` passes that repository and file tuple to `install_artifacts` (patch it); `verify_model(root / PARAKEET_MODEL)` accepts a directory with those five files and a matching manifest and rejects one with `model.bin` instead; `Config(model=PARAKEET_MODEL).validate()` passes; `staging_path(PARAKEET_MODEL, root, "a" * 32)` is accepted.
- [ ] **Step 2: Run** `-m pytest tests/test_models.py tests/test_config.py -q`. Expected: fail.
- [ ] **Step 3: Implement** the catalog and installer changes.
- [ ] **Step 4: Dependency.** Add `"onnx-asr==0.12.0"` and `"onnxruntime>=1.18.1,<2"` to `pyproject.toml` dependencies; add the line `onnx-asr==0.12.0` to `requirements-dev.lock` in alphabetical position (the `onnxruntime` pin already there is unchanged). Install: `uv pip install --python .venv\Scripts\python.exe --no-deps onnx-asr==0.12.0`. Verify: `.venv/Scripts/python.exe -c "import onnx_asr; print(onnx_asr.__name__)"` prints `onnx_asr`.
- [ ] **Step 5: Packaging and notices.** Add `"onnx_asr"` to the `collect_all` package tuple in `packaging/localphraser.spec`. Add rows to `THIRD_PARTY_NOTICES.md` and `docs/bundled-dependencies.md`: onnx-asr, MIT, `https://github.com/istupakov/onnx-asr`; Parakeet TDT 0.6b v2, CC-BY-4.0, NVIDIA, ONNX conversion by istupakov at `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`, downloaded by the user and not bundled. Update `tests/test_bundle_inventory.py` expectations if it lists packages.
- [ ] **Step 6: Run the full checks.** Expected: all pass.
- [ ] **Step 7: Commit** `Add Parakeet to the model catalog, installer and bundle`.

### Task 7: Parakeet recogniser and the recogniser factory

**Files:**
- Create: `src/localphraser/parakeet.py`, `tests/test_parakeet.py`
- Modify: `src/localphraser/recognition.py`, `src/localphraser/ui.py` (`make_pipeline`), `src/localphraser/diagnostics.py`, `scripts/benchmark_recognition_quality.py`, `scripts/benchmark_quiet_speech.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `config.PARAKEET_MODEL`, `config.inference_threads`, `models.verify_model`.
- Produces: `parakeet.ParakeetRecognizer(model_path: Path, cpu_threads: int = 0, vocabulary: str = "")` with `vocabulary`, `preview_ready`, `prepare()`, `transcribe(audio) -> str`, `transcribe_stream(audio, partial=None) -> str`, `warm_preview()`, `preview(audio) -> str`.
- Produces: `parakeet.split_long(audio: Audio) -> list[Audio]` (views, in order, concatenating to the input), `parakeet.restore_spelling(text: str, vocabulary: str) -> str`.
- Produces: `recognition.make_recognizer(root: Path, model: str, cpu_threads: int, vocabulary: str, quality: str) -> Recognizer`.

Rules the tests do not fully determine:
- `split_long`: while more than 30 s remain, look at 200 ms windows starting every 10 ms from 20.0 s to 29.8 s of the remainder, take the one with the lowest mean absolute value (the first on a tie), and cut at its centre.
- `restore_spelling`: terms are the comma-separated vocabulary entries, trimmed. A term's key is its casefolded text with spaces and hyphens removed. Split the text on whitespace. For each word, the leading and trailing characters from `.,;:!?"'()[]{}…` are its punctuation and the rest is its core. At each position try spans of 4, 3, 2, then 1 words. A span matches when no word inside it has punctuation facing another word of the span and the key of the joined cores equals a term's key. Replace the span with the first word's leading punctuation, the term as approved, and the last word's trailing punctuation. No regular expressions built from terms.
- `prepare`: set `HF_HUB_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1`, call `verify_model(path)`, then `onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2", str(path), quantization="int8", sess_options=options, providers=["CPUExecutionProvider"])` with `options.intra_op_num_threads = inference_threads(cpu_threads)` and `options.inter_op_num_threads = 1`. Imports of `onnx_asr` and `onnxruntime` stay inside `prepare`.
- Decoding one piece: `self._model.recognize(piece, sample_rate=16000)`, stripped. Pieces are joined with one space, then `restore_spelling` runs once on the whole text. `partial`, when given, receives the restored text so far after each piece.
- `warm_preview` recognises one second of zeros and discards the result. `preview` returns `""` until `preview_ready`, and otherwise decodes the audio it is given without cutting.

- [ ] **Step 1: Write the failing tests** in `tests/test_parakeet.py`

```python
RATE = 16000

def test_short_audio_is_one_piece():
    audio = np.zeros(30 * RATE, dtype=np.float32)
    assert [p.size for p in split_long(audio)] == [30 * RATE]

def test_long_audio_is_cut_at_the_quietest_window_between_20_and_30_seconds():
    rng = np.random.default_rng(0)
    audio = rng.normal(0, 0.05, 70 * RATE).astype(np.float32)
    audio[int(24.0 * RATE) : int(24.4 * RATE)] = 0            # a pause
    pieces = split_long(audio)
    assert abs(pieces[0].size - int(24.2 * RATE)) <= int(0.11 * RATE)
    assert all(p.size <= 30 * RATE for p in pieces)
    assert np.array_equal(np.concatenate(pieces), audio)
    assert all(np.shares_memory(p, audio) for p in pieces)

def test_steady_noise_and_exact_boundary_still_cover_every_sample_once():
    rng = np.random.default_rng(1)
    for seconds in (30, 30.01, 95):
        audio = rng.normal(0, 0.05, int(seconds * RATE)).astype(np.float32)
        pieces = split_long(audio)
        assert np.array_equal(np.concatenate(pieces), audio)
        assert all(0 < p.size <= 30 * RATE for p in pieces)

@pytest.mark.parametrize("text,vocabulary,expected", [
    ("I use local phraser daily.", "LocalPhraser", "I use LocalPhraser daily."),
    ("pyside, and Codex.", "PySide, Codex", "PySide, and Codex."),
    ("(local-phraser)", "LocalPhraser", "(LocalPhraser)"),
    ("the local, phraser", "LocalPhraser", "the local, phraser"),
    ("local phrase", "LocalPhraser", "local phrase"),
    ("we tried c++ and Node.JS.", "C++, node.js", "we tried C++ and node.js."),
    ("new york city is big", "New York, New York City", "New York City is big"),
    ("nothing to change", "", "nothing to change"),
    ("", "LocalPhraser", ""),
])
def test_restore_spelling(text, vocabulary, expected):
    assert restore_spelling(text, vocabulary) == expected

def test_transcribe_decodes_pieces_in_order_and_reports_partials():
    recognizer = ParakeetRecognizer(Path("unused"), vocabulary="LocalPhraser")
    recognizer._model = Mock(recognize=Mock(side_effect=[" one local", "phraser two ", "three"]))
    rng = np.random.default_rng(2)
    partials = []
    text = recognizer.transcribe_stream(
        rng.normal(0, 0.05, 70 * RATE).astype(np.float32), partials.append)
    assert text == "one LocalPhraser two three"
    assert partials[-1] == text and len(partials) == 3
    assert all(c.kwargs == {"sample_rate": 16000} for c in recognizer._model.recognize.call_args_list)

def test_prepare_verifies_then_loads_local_int8_files_offline(monkeypatch, tmp_path):
    # patch localphraser.models.verify_model, onnx_asr.load_model, config.thread_limit -> 6
    # ParakeetRecognizer(tmp_path, cpu_threads=16).prepare()
    # assert verify called with tmp_path before load_model
    # assert load_model args == ("nemo-parakeet-tdt-0.6b-v2", str(tmp_path))
    # assert kwargs["quantization"] == "int8", kwargs["providers"] == ["CPUExecutionProvider"]
    # assert kwargs["sess_options"].intra_op_num_threads == 6
    # assert os.environ["HF_HUB_OFFLINE"] == "1"; second prepare() does not load again

def test_preview_is_empty_until_warm_then_decodes_without_cutting():
    recognizer = ParakeetRecognizer(Path("unused"))
    recognizer._model = Mock(recognize=Mock(return_value="words"))
    assert recognizer.preview(np.zeros(RATE, dtype=np.float32)) == ""
    recognizer.warm_preview()
    assert recognizer.preview_ready and recognizer.preview(np.zeros(RATE, dtype=np.float32)) == "words"

@pytest.mark.skipif(not os.environ.get("LOCALPHRASER_TEST_PARAKEET"), reason="No local Parakeet model")
def test_real_parakeet_loads_and_hears_nothing_in_silence_with_network_denied(monkeypatch):
    # deny socket.connect / connect_ex as tests/test_recognition_offline.py does
    recognizer = ParakeetRecognizer(Path(os.environ["LOCALPHRASER_TEST_PARAKEET"]))
    assert recognizer.transcribe(np.zeros(RATE, dtype=np.float32)) == ""

def test_factory_picks_the_engine_by_model_name(tmp_path):
    assert isinstance(make_recognizer(tmp_path, "parakeet-tdt-0.6b-v2", 0, "A", "fast"), ParakeetRecognizer)
    whisper = make_recognizer(tmp_path, "small.en", 0, "A", "fast")
    assert isinstance(whisper, WhisperRecognizer) and whisper.path == tmp_path / "small.en"
    assert whisper.beam_size == 1 and whisper.vocabulary == "A"
```

- [ ] **Step 2: Run** `-m pytest tests/test_parakeet.py -q`. Expected: import error.
- [ ] **Step 3: Implement** `parakeet.py` and `make_recognizer` (it imports `parakeet` lazily).
- [ ] **Step 4: Use the factory** in `Controller.make_pipeline`, `diagnostics.runtime_check` (patch target in `tests/test_diagnostics.py` becomes `diagnostics.make_recognizer`), `scripts/benchmark_recognition_quality.py` (Parakeet runs once per case, labelled quality `"n/a"`) and `scripts/benchmark_quiet_speech.py`.
- [ ] **Step 5: Run the full checks.** Then run the opt-in test against the trial files, which have no manifest, by installing the model properly first: `.venv/Scripts/python.exe -m localphraser install-model parakeet-tdt-0.6b-v2 --root C:/Users/robbi/Projects/LocalPhraser/.cache/models` (661 MB, into the development model directory), then `LOCALPHRASER_TEST_PARAKEET=C:/Users/robbi/Projects/LocalPhraser/.cache/models/parakeet-tdt-0.6b-v2 .venv/Scripts/python.exe -m pytest tests/test_parakeet.py -q`. Expected: all pass, none skipped.
- [ ] **Step 6: Commit** `Add Parakeet recogniser with long-recording cuts and spelling restore`.

### Task 8: Make Parakeet the default and fit it into the UI

**Files:**
- Modify: `src/localphraser/config.py`, `src/localphraser/main.py:29,33,61`, `src/localphraser/pipeline.py` (`warm_live_preview`), `src/localphraser/ui.py` (Settings form near 316-340, `prepare_live_preview`, `start_first_launch_setup`, `show_vocabulary`), `src/localphraser/vocabulary.py`, `packaging/START_HERE.txt`, `docs/release-checklist.md`
- Test: `tests/test_config.py`, `tests/test_first_launch.py`, `tests/test_main.py`, `tests/test_pipeline.py`, `tests/test_dropdowns.py`, `tests/test_vocabulary.py`

**Interfaces:**
- Consumes: `config.PARAKEET_MODEL`, `make_recognizer`.
- Produces: `config.DEFAULT_MODEL = PARAKEET_MODEL`, used by `Config.model` and the three `main.py` argument defaults. `Dictation(..., warm_on_start: bool = False)`. `VocabularyPage(history, current, save, engine_note: Callable[[], str])`.

Exact copy:
- First-launch notice: "First launch: downloading the default Parakeet speech model (~660 MB) from Hugging Face. Internet is needed for this setup only. You can cancel; retry using Download speech model. Dictation becomes available when installation finishes. Already have models? Cancel, then choose their directory and Save."
- Quality hint while Parakeet is selected: "Recognition quality applies to Whisper models only."
- Vocabulary note, Whisper: "Whisper models use these terms as recognition hints."
- Vocabulary note, Parakeet: "Parakeet restores the spelling of these terms when it hears them exactly. It does not correct sound-alike words."
- `packaging/START_HERE.txt` line 8: "3. A new profile downloads the Parakeet speech model (~660 MB) automatically in Settings. This first setup needs internet."

- [ ] **Step 1: Write the failing tests**
  - `Config().model == "parakeet-tdt-0.6b-v2"`; a saved config with `"model": "base.en"` still loads as `base.en`.
  - `main` argument defaults for `install-model`, `verify-model` and the runtime check are `DEFAULT_MODEL`.
  - `tests/test_first_launch.py`: replace the `base.en` expectations at the default-profile assertions with `DEFAULT_MODEL`; the setup notice equals the copy above.
  - Pipeline: with `warm_on_start=True` and `live_preview=False`, `warm_live_preview()` returns `True`, enters `State.WARMING`, calls the recogniser's `warm_preview`, and returns to `IDLE`; with both false it returns `False` as today.
  - Desktop: with a Parakeet config and the model present, `prepare_live_preview()` warms even though `live_preview` is false; with a Whisper config and `live_preview` false it does not.
  - Settings: selecting Parakeet in the model combo disables the quality combo and shows the hint above; selecting `small.en` enables it and restores the previous hint.
  - Vocabulary page: the note label shows the string returned by `engine_note` after `refresh()`.
- [ ] **Step 2: Run** the listed test files. Expected: new tests fail.
- [ ] **Step 3: Implement.** In `warm_live_preview` the `not self.live_preview` condition becomes `not (self.live_preview or self.warm_on_start)`. `make_pipeline` passes `warm_on_start=config.model == PARAKEET_MODEL`. `prepare_live_preview` uses `config.live_preview or config.model == PARAKEET_MODEL`. `show_vocabulary` passes a callable choosing the note from `self.config.model`.
- [ ] **Step 4: Update** `packaging/START_HERE.txt`, `docs/release-checklist.md` wherever they name `base.en` as the automatic download, and any test that pins those lines.
- [ ] **Step 5: Run the full checks.** Expected: all pass.
- [ ] **Step 6: Commit** `Make Parakeet the default engine and adapt settings, start-up and vocabulary`.

### Task 9: Measure, decide temperature retry, record the evidence

**Files:**
- Modify: `src/localphraser/recognition.py` (only if the rule below says so), `docs/testing.md`, `docs/roadmap.md`, `docs/model-options-and-latency.md`, `docs/architecture.md`, `docs/privacy.md`, `docs/development.md`, `README.md`

- [ ] **Step 1: Install `small.en` and `base.en` if missing** from `.cache/models` (`-m localphraser verify-model <name> --root .cache/models`; install only when verification fails).
- [ ] **Step 2: Run the benchmark**, nothing else running from this session: `.venv/Scripts/python.exe scripts/benchmark_quiet_speech.py --root .cache/models --models base.en small.en parakeet-tdt-0.6b-v2 --temp-dir .cache/quality-bench --retry > .cache/quality-bench/quiet-speech.json`.
- [ ] **Step 3: Run the long clip** in its own process: same command with `--models parakeet-tdt-0.6b-v2 --long`, output to `.cache/quality-bench/quiet-speech-long.json`.
- [ ] **Step 4: Check against "What counts as done" in the spec.**
  - Parakeet at peaks 0.02 and 0.014, continuous and paused: at most 5 errors per 100 words. Normal level: no worse than the spec's `base.en` as-shipped row (0.0 / 2.3).
  - `words_invented` is all zeros for every row, including the `+retry` rows.
  - Long clip: `peak_mb` under 1331 (1.3 GB) and errors per 100 words 0. If memory is over, change the piece limit to 20 s with the search from 12 s, rerun Step 3 once. If still over, stop and report the numbers to the user; do not continue.
  - Any other miss: stop and report the numbers to the user.
- [ ] **Step 5: Decide temperature retry.** Set `WhisperRecognizer.temperatures` default to `(0.0, 0.2, 0.4)` only if all three hold for `small.en+retry` against `small.en`: lower errors at peak 0.008 (continuous and paused summed); zero invented words; `seconds_per_clip` at peaks 0.25 and 0.02 not more than 10% higher. Otherwise leave `(0.0,)`. If changed, update the default-temperature test from Task 2 and rerun the full checks.
- [ ] **Step 6: Record.** Add a dated section to `docs/testing.md` with the machine, its load, the two result tables and the retry decision with its numbers; add a roadmap entry in the existing narrative style. Correct the documents that now say something untrue: recognition is Whisper only; startup is lazy for every model; "Recognition output is not post-replaced"; the default model and its download size; the thread setting. State plainly that the evidence is synthetic speech and that human speech is not yet verified.
- [ ] **Step 7: Run the full checks** and commit `Record quiet-speech benchmark results and update engine documentation`.

### Task 10: Development build and hand-over

**Files:** none in the repository unless a check fails.

- [ ] **Step 1: Confirm the development profile** exists at `.cache/development-profile/config.json`. Read only that file. Set its `"model"` to `"parakeet-tdt-0.6b-v2"` and `"cpu_threads"` to `0`, and confirm its `model_root` holds the Parakeet model from Task 7 (install it there with `install-model --root <that model_root>` if it is a different directory).
- [ ] **Step 2: Build** `.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath .cache/development-build --workpath .cache/development-work packaging/localphraser.spec`. Expected: exit 0, and `git status` shows nothing under `dist/` changed.
- [ ] **Step 3: Frozen smoke** with a disposable config directory under `.cache`: `.cache/development-build/LocalPhraser/LocalPhraser.exe --smoke-test --config <absolute disposable path>/config.json`. Expected: exit 0.
- [ ] **Step 4: Frozen runtime check with Parakeet** using the app's own runtime-check command (see `main.py`, the parser at line 61) with `--model parakeet-tdt-0.6b-v2`, the development model root and a new report path under `.cache`. Expected: report `"status": "passed"`. This proves `onnx_asr` and its data files are in the bundle.
- [ ] **Step 5: Tell the user** the development build is ready: how to start it (the command in `docs/development.md`), that the shortcut is Ctrl+Shift+F11 and results appear in Latest transcript, what to try (normal, quiet, slow with pauses), and that switching the stable app is a separate step that waits for their word.

---

## Out of scope for this plan

Replacing `dist/LocalPhraser` and changing the user's own profile. That happens only after the user has tried the development build and asks for the switch; the launcher path stays the same.
