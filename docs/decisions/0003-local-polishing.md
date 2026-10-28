# 0003 — Optional local polishing with bounded execution

Status: implemented experimental build; real-voice acceptance pending.

Keep Raw mode independent and default. Use optional llama-cpp-python CPU inference with
publisher Qwen2.5 Q4_K_M GGUFs, explicitly downloaded with pinned provenance and SHA-256.
The publisher declares Apache-2.0 for both selected sizes; bindings/runtime are MIT.
Official source links and alternatives are recorded in research.md.

Five fixed-text trials favored 1.5B preservation over 0.5B at higher memory/latency cost;
choose 1.5B initially and retain the lighter model as an option. No claim extends beyond
the measured cases. Do not turn the model into a silent automatic word-correction layer.

Run inference in a lazy warm spawn process over private pipes. This adds one process, but
allows native work to be terminated on timeout or exit without an HTTP server. Raw and
result text remain in RAM only. Enforce character, context, generation and time limits.
Treat dictated instructions as text and reject word/number additions, removals or reordering,
except explicitly permitted hesitation tokens. Failure returns raw without provider errors.

Lexical preservation is deliberately conservative: paraphrases, spelling changes and richer
grammar repair fall back to Raw. Punctuation/case can still alter meaning, and filler
classification can be ambiguous; expose the original and label Polished experimental.
Custom instructions do not relax the guard. Broader correction requires stronger evaluation.

A Windows stress test reproduced a native INVALID_HANDLE failure when one thread closed
a multiprocessing pipe while another polled it. The reader now closes its own handle;
shutdown terminates the child to wake the reader with EOF. Tests cover this lifecycle.

Remaining work: real-voice cross-app trials, a larger preservation/quality corpus, context
budget ergonomics, signed/clean-machine packaging, and exact bundled license inventory.
