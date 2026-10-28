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
are functionality checks, not speed/accuracy benchmarks. Phase 2 refinement latency is N/A.

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
