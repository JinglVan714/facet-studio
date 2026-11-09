# Third-party notices

This repository's own code is licensed under the MIT License (see `LICENSE`).
The following components are **not vendored**; they are installed or cloned
separately. Their licenses apply to their own code. This list is a practical
inventory, not legal advice; re-check upstream licenses before redistribution.

## Runtime / build dependencies

| Component | License | Use |
|---|---|---|
| [LibreChat](https://github.com/danny-avila/LibreChat) | MIT | Chat shell; external clone, not vendored |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | Workflow StateGraph / checkpoint |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT | MCP server/client |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Preview/run detail HTTP service |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI server |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Data models |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | Apache-2.0 | OpenAI-compatible provider client |
| [Pandoc](https://pandoc.org/) | GPL-2.0-or-later | Markdown → PDF pipeline (external binary) |
| [Tectonic](https://tectonic-typesetting.github.io/) | MIT | XeLaTeX engine (external binary) |
| [Playwright](https://github.com/microsoft/playwright) | Apache-2.0 | PDF SVG rendering / XHS cards |
| [Pillow](https://python-pillow.org/) | HPND | Image handling / card validation |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | PDF page-count checks |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | MIT | Markdown rendering |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | Video download |
| [DashScope SDK](https://github.com/aliyun/alibabacloud-bailian-speech-demo) | Apache-2.0 | ASR / VLM calls |
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause | Media decoding |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause | FFmpeg binary helper (FFmpeg build license may differ) |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | BSD-3-Clause | Scene detection |
| [ImageHash](https://github.com/JohannesBuchner/imagehash) | BSD-2-Clause | Frame deduplication |
| [NumPy](https://numpy.org/) | BSD-3-Clause | Numeric helpers |
| [tiktoken](https://github.com/openai/tiktoken) | MIT | Token counting |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | Tests |

## Writing-method references

`skills/writing/reader_first_explainer/SOURCES.md` and
`skills/writing/video-article/README.md` record the method-level sources.
The text in this repository is an original composition; the sources below are
method references, not verbatim copies:

- MIT-licensed writing skills (great-writer, writing-pipeline-zh,
  research-writing-skill, rednote-writing-skill, avoid-ai-writing,
  stop-slop-zh, wewrite, mattpocock/skills, drama-skills).
- Anthropic `doc-coauthoring` (per-folder license; method only).
- Local `bilibili-render-pdf` skill: **no LICENSE file was found** in the local
  copy; only pedagogical flow/frame-selection method was referenced, no text
  copied. `integrations/pdf/facet-template.tex` is an independent LaTeX
  adaptation of a local course-notes template; re-check before commercial
  redistribution or replace with a fully original template.

## Content / media

- Bilibili videos referenced in examples remain the property of their
  uploaders. The public repository does **not** include Bilibili video frames,
  covers, or full transcripts. See `examples/NOTICE.md`.
- `deliverables/writing-skill/` (historical articles-only sample with Bilibili
  frames) is intentionally excluded from the public repository.
