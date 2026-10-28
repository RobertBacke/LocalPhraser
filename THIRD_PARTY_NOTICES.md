# Third-party licenses and provenance

LocalPhraser's original source is MIT, Copyright (c) 2026 Robert Backe. Dependencies,
model weights, and native libraries retain separate terms. No third-party application code,
branding or weights are committed here.

| Component | Upstream / declared terms |
| --- | --- |
| Qt for Python / PySide6 Essentials / Shiboken | [Qt licenses](https://doc.qt.io/qtforpython-6/licenses.html); LGPLv3/GPL/commercial choices; use eligible dynamically linked LGPL components |
| faster-whisper | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) |
| CTranslate2 | [MIT](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) |
| Whisper models | [MIT](https://github.com/openai/whisper/blob/main/LICENSE); Systran conversion [model card](https://huggingface.co/Systran/faster-whisper-base.en) |
| Silero VAD | [MIT](https://github.com/snakers4/silero-vad/blob/master/LICENSE); ONNX asset supplied by faster-whisper |
| NumPy | [BSD](https://numpy.org/doc/stable/license.html); bundled BLAS terms also apply |
| sounddevice / PortAudio | [MIT](https://github.com/spatialaudio/python-sounddevice/blob/master/LICENSE) / [PortAudio license](https://www.portaudio.com/license.html) |
| UIAutomation Python wrapper | [Apache-2.0](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows/blob/master/LICENSE) |
| Hugging Face Hub / tokenizers | [Apache-2.0](https://github.com/huggingface/huggingface_hub/blob/main/LICENSE) / [Apache-2.0](https://github.com/huggingface/tokenizers/blob/main/LICENSE) |
| ONNX Runtime | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| PyAV / FFmpeg | [PyAV BSD](https://github.com/PyAV-Org/PyAV/blob/main/LICENSE.txt); FFmpeg build-dependent LGPL/GPL terms must be reviewed before release |
| PyInstaller | [GPL with bootloader exception](https://pyinstaller.org/en/stable/license.html) |
| Optional llama-cpp-python / llama.cpp | [MIT bindings](https://github.com/abetlen/llama-cpp-python/blob/main/LICENSE.md) / [MIT runtime](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE) |
| Optional Qwen2.5 0.5B / 1.5B Instruct GGUF | Publisher-declared [Apache-2.0](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/main/LICENSE); model LICENSE and README are explicitly downloaded and verified |
| Optional Jinja2 / MarkupSafe / diskcache | BSD-3-Clause / BSD-3-Clause / Apache-2.0; included runtime metadata retains their licenses |

This table is a contributor inventory, not a substitute for complete bundled notices.
Do not publicly distribute a build until exact wheel/native-library terms, copyright notices,
Qt replacement/source obligations and FFmpeg build configuration are reviewed. The build
collects available installed license files; missing notices/source offers still require review.
No application license grants model redistribution rights beyond the model's own license.
