# Marginalia

Upload a research paper. Gemma 4 reviews it and pins every flaw to the exact sentence it came from, with a concrete fix. It also summarises the paper and checks the references.

Gemma 4 is called through the **Gemini API** (Google AI Studio), so there is nothing to download and no GPU is needed.

## Setup

1. Get a free API key at https://aistudio.google.com/apikey
2. Copy `.env.example` to `.env` and paste the key:
   ```
   GEMINI_API_KEY=your_key_here
   ```
3. Install and run:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python run.py
   ```

The browser opens at http://127.0.0.1:8000. The status pill (top right) turns green when the key is loaded. Hover over it if it turns red.

## Models

Set `GEMMA_MODEL` in `.env`.

| Model id | Notes |
|---|---|
| `gemma-4-26b-a4b-it` (default) | faster, lighter on rate limits |
| `gemma-4-31b-it` | strongest critique |

Other settings: `MAX_NEW_TOKENS` (4096), `CHUNK_CHARS` (16000), `CROSSREF_MAILTO` (your email, for Crossref), `PORT` (8000). Rate-limit errors (429) are retried automatically with backoff, so a free-tier key may just make long papers slower.

## How it stays accurate

1. **Parsing.** PDF text is read block by block with column-aware ordering. Headers, footers and the reference list are separated from the body.
2. **Chunked review.** Long papers are split along section boundaries. Each chunk is reviewed with the abstract as context.
3. **Verbatim anchoring.** Every finding must quote the paper. The quote is located in the document text, so each flaw is highlighted in place. Findings whose quote cannot be found are hidden by default and flagged as unverified.
4. **Cross-section pass.** A separate pass compares abstract and conclusion claims against the rest of the paper, to catch overclaiming and contradictions.
5. **Deduplication, severity ranking, and a calibrated verdict** built only from the confirmed findings.
6. **Citations.** In-text markers (`[3]`, `[1–4]`, `(Smith et al., 2020)`) are matched to the reference list to find dangling and uncited entries and duplicates. References are optionally looked up on Crossref (title and year match, DOI check).

## Network use

The paper text is sent to the Gemini API for analysis, so don't upload anything you are not allowed to share with Google. The optional Crossref lookup sends only reference strings (untick the box in the UI to disable it).

## Limits

- Scanned PDFs need OCR first. No OCR is included.
- The model can still miss flaws or misjudge them. Treat the output as a thorough first reviewer, not a verdict. The quote and fix are always shown so you can check each one.
- "Unverified" on a reference means no close Crossref match. Preprints, books and many conference papers are not indexed there.
- Equations, tables and figures are only seen as extracted text.

## Layout

```
run.py            launcher
app/main.py       FastAPI server and job runner
app/analysis.py   review pipeline, quote grounding, dedupe
app/prompts.py    all prompts
app/parse.py      PDF/DOCX/TXT reading and section chunking
app/citations.py  reference parsing, cross-checks, Crossref
app/llm.py        Gemma 4 via the Gemini API (google-genai)
static/           the UI
```
