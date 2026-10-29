# Performance objectives and evaluation

Provisional targets for a modern 4-core / 8 GB Windows laptop; **not measured claims**:

| Metric | Initial target |
| --- | --- |
| Idle CPU, 60-second average | < 1% of total system CPU |
| Idle RAM before loading a model | < 200 MiB working set |
| Warm microphone activation | < 150 ms |
| Warm base.en, 10 s speech → insertion | < 3 s after release |
| Cold model load | < 5 s |
| Peak app working set, base.en | < 1 GiB |

Cold start must be reported separately from warm inference. `scripts/benchmark.py` measures
local WAV decoding/model load+first inference and subsequent inference, capturing hardware,
OS, model and process working-set observations. No transcripts are printed or saved.
It does not measure microphone startup, GUI idle use, human speech accuracy, or text delivery.
Collect those with Windows Performance Monitor and controlled manual runs. Run 30 samples
per tiny/base/small model, same speech corpus, greedy beam=1, CPU INT8, fixed threads; report
median/p95, peak RAM, cold/warm and actual model revision. Use explicit consent for audio
fixtures and keep them out of version control.

No benchmark results exist yet for the complete real-speech pipeline. Synthetic silence runs
are functionality checks, not speed/accuracy benchmarks. Phase 2 observations follow below.

## Actual synthetic-speech sanity run — 2026-10-28

Windows 11 build 26200, AMD64 Family 25 Model 117 Stepping 2, 12 logical CPUs, 15.3 GiB
visible RAM; Python 3.12.12, faster-whisper 1.2.1, CTranslate2 4.8.4, CPU INT8 / four threads.
Model: Systran/faster-whisper-base.en, revision
`3d3d5dee26484f91867d81cb899cfcf72b96be6c`.
`scripts/synthetic_speech_check.py` generated a fixed nonpersonal sentence with installed
Windows SAPI, decoded it to 16 kHz mono, denied Python socket connections, and checked for
expected recognition words. Cold load+first transcription: **1.855 s**; warm transcription:
**0.630 s**. Both passed. These are single observations from a synthetic fixture, with model
libraries imported before timing. They are not end-to-end latency or a statistical benchmark.
No microphone activation, idle CPU/RAM, peak memory or LLM latency was measured in this run.

The clean unsigned Windows development folder build measured **310.3 MiB** on disk, excluding
the separately downloaded speech model. This is a folder size measurement, not compressed
installer size or process memory usage. Clean frozen GUI smoke launch exited successfully.

## Actual activation observations — interaction update

Same host as above; system-default input, sounddevice 0.5.6, requested low latency,
16 kHz mono float32. `scripts/benchmark_capture.py` briefly captured in RAM, reported only
timing, cleared buffers, and never transcribed or saved audio. Three trials per path:

| Stream handling | Start returned (ms) | First callback observed (ms) |
| --- | --- | --- |
| Reopen per recording | 895.21, 35.97, 34.85 | 1202.04, 343.21, 331.13 |
| Prepared and reused | 0.73, 0.68, 0.79 | 291.92, 19.87, 17.45 |

The first reopen includes sounddevice initialization; this is not a controlled before/after
benchmark of the entire old/new app. Callback arrival includes backend buffering and does
not establish the physical first-sample timestamp. These observations do not prove opening
words will never be clipped. There is no background capture; the first start after device
preparation can still have driver latency. Human immediate-speech acceptance remains pending.

## Phase 2 CPU refinement observations — 2026-10-28

Same host and Python as above, llama-cpp-python 0.3.36 CPU wheel, four threads, Q4_K_M,
4,096-token context, deterministic temperature 0, 1,024 output-token cap, default prompt.
`scripts/benchmark_refinement.py` used five fixed nonsensitive texts with Python socket
connections disabled in the worker. Each cell is one observation, not a percentile or a
controlled hardware comparison; other development activity may affect timings.

| Fixed case | 0.5B seconds / outcome | 1.5B seconds / outcome |
| --- | --- | --- |
| Punctuation, cold process/model | 2.772 / accepted edit | 5.329 / accepted edit |
| Filler, warm | 0.494 / accepted edit | 1.015 / accepted edit |
| Numbers, warm | 0.690 / raw fallback | 1.469 / accepted edit |
| Technical terms, warm | 0.558 / accepted edit | 1.229 / accepted edit |
| Instruction-like text, warm | 15.081 / timeout/raw | 0.976 / accepted edit |

Peak sampled child RSS (50 ms sampling, excludes parent/ASR/UI): **572.4 MiB** for 0.5B,
**1,773.1 MiB** for 1.5B. These are observed process working sets, not a total application
memory bound. The model stays resident while Polished remains selected after first use;
switching to Raw or exit releases it. Guard rejections retain a healthy warm worker;
timeouts terminate it, so the following attempt incurs another cold start.

Publisher revisions: 0.5B `9217f5db79a29953eb74d5343926648285ec7e67`;
1.5B `91cad51170dc346986eccefdc2dd33a9da36ead9`. Download manifests also record GGUF,
LICENSE and README SHA-256 values. The 1.5B model preserved the lexical content of all five
samples; that small result supports the initial choice but does not certify meaning,
accuracy, adversarial robustness, or real-voice quality.

`synthetic_speech_check.py` additionally passed generated Windows SAPI speech through
`small.en` ASR and 1.5B polishing with Python connections denied. Combined cold ASR+polish
was **10.299 s**, warm **3.172 s**. Audio generation/decoding occurs before those timings;
microphone activation, target verification, and insertion are excluded. No personal audio
or transcripts were recorded or printed. Real microphone end-to-end p50/p95 remains open.

## Overlapping first-use model loading

On the same host, `benchmark_refinement.py --prepare-lead 4` starts the 1.5B child, waits
four seconds to simulate speaking time, then submits the same fixed texts. First-request
wait after submission was **1.661 s**, versus the previous cold observation of 5.329 s.
The four-second lead is excluded from 1.661 s: total work was not reduced, and these are
not controlled end-to-end microphone measurements. The following requests took 0.916,
1.442, 1.133 and 0.922 s, respectively; all five edits passed the unchanged guard.
Sampled peak child RSS was 1,773.0 MiB. Preparation can hide cold loading during speech,
but does not speed up warm token generation or eliminate ASR processing time.

The Phase 3 unsigned portable ZIP measured **121.1 MiB**, excluding ASR/LLM setup downloads.
This is a compressed artifact size, distinct from the earlier folder size and process RSS.
The ZIP retains shared libraries and bundled dependency notices; compression is not a
runtime resource optimization. Broader idle/peak/end-to-end profiling remains open.
