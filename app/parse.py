import re
from pathlib import Path

LIG = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl", "\u00ad": "", "\u200b": ""}
FOLD = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-", "\u00a0": " ",
})

NAMES = (
    r"abstract|introduction|related work|background|preliminaries|literature review|methods?|methodology|"
    r"materials and methods|experimental setup|experiments?|results?|results and discussion|evaluation|"
    r"analysis|discussion|limitations|conclusions?|conclusions? and future work|future work|"
    r"acknowledg(?:e)?ments?|references|bibliography|appendix(?:es)?(?: [a-z0-9]+)?|supplementary material"
)
KNOWN = re.compile(rf"^(?:(?:\d{{1,2}}(?:\.\d{{1,2}})*\.?|[IVX]{{1,4}}\.?)\s+)?(?:{NAMES})\s*[:.]?$", re.I)
NUMBERED = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.?\s+[A-Z][^.!?]{2,70}$")
LEAD = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})*\.?|[IVX]{1,4}\.?)\s+")


def clean(s):
    for k, v in LIG.items():
        s = s.replace(k, v)
    return s


def fold(s):
    return clean(s).translate(FOLD)


def is_heading(p):
    return len(p) <= 80 and "\n" not in p and bool(KNOWN.match(p) or (NUMBERED.match(p) and len(p.split()) <= 9))


def _tidy(p):
    return " ".join(clean(p).split())


def _order_blocks(blocks, width):
    cols = [b for b in blocks if (b[2] - b[0]) < width * 0.55]
    left = sum(1 for b in cols if (b[0] + b[2]) / 2 < width / 2)
    right = len(cols) - left
    if left < 3 or right < 3:
        return sorted(blocks, key=lambda b: (b[1], b[0]))
    out, lbuf, rbuf = [], [], []
    for b in sorted(blocks, key=lambda b: b[1]):
        if (b[2] - b[0]) >= width * 0.6:
            out += lbuf + rbuf + [b]
            lbuf, rbuf = [], []
        elif (b[0] + b[2]) / 2 < width / 2:
            lbuf.append(b)
        else:
            rbuf.append(b)
    return out + lbuf + rbuf


def _read_pdf(path):
    import fitz

    paras = []
    with fitz.open(path) as pdf:
        for page in pdf:
            h, w = page.rect.height, page.rect.width
            blocks = [b for b in page.get_text("blocks") if b[6] == 0]
            for b in _order_blocks(blocks, w):
                t = _tidy(re.sub(r"(\w)-\n(\w)", r"\1\2", b[4]))
                if len(t) < 3 or t.isdigit():
                    continue
                if (b[1] < h * 0.05 or b[3] > h * 0.95) and len(t) < 80:
                    continue
                paras.append(t)
    return paras


def _read_docx(path):
    import docx

    return [_tidy(p.text) for p in docx.Document(path).paragraphs if p.text.strip()]


def _read_text(path):
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    return [_tidy(p) for p in re.split(r"\n\s*\n", raw) if p.strip()]


def read_document(path):
    ext = Path(path).suffix.lower()
    paras = _read_pdf(path) if ext == ".pdf" else _read_docx(path) if ext == ".docx" else _read_text(path)
    return "\n\n".join(p for p in paras if p)


def _split_long(text, start, end, limit):
    spans = []
    while end - start > limit * 1.5:
        cut = text.rfind(". ", start + int(limit * 0.7), start + int(limit * 1.2))
        cut = cut + 2 if cut > 0 else start + limit
        spans.append((start, cut))
        start = cut
    spans.append((start, end))
    return spans


def structure(text, limit):
    sections = [{"title": "Front matter", "start": 0, "ref": False}]
    units, heads, pos, cur = [], [], 0, 0
    for p in text.split("\n\n"):
        s, e = pos, pos + len(p)
        pos = e + 2
        head = is_heading(p)
        if head:
            sections.append({"title": LEAD.sub("", p).strip(" :.").title(), "start": s, "ref": False})
            cur = len(sections) - 1
            heads.append([s, e])
        units.append({"s": s, "e": e, "sec": cur, "head": head})
    for i, sec in enumerate(sections):
        sec["end"] = sections[i + 1]["start"] if i + 1 < len(sections) else len(text)

    ref_idx = None
    for i, sec in enumerate(sections):
        if re.match(r"^(references|bibliography)$", sec["title"], re.I):
            ref_idx = i
    ref_ranges = []
    if ref_idx is not None:
        for i in range(ref_idx, len(sections)):
            if i > ref_idx and re.match(r"^(appendix|supplement)", sections[i]["title"], re.I):
                break
            sections[i]["ref"] = True
            ref_ranges.append((sections[i]["start"], sections[i]["end"]))
    refs_text = "\n\n".join(
        text[a:b].split("\n\n", 1)[1] if "\n\n" in text[a:b] else "" for a, b in ref_ranges[:1]
    )

    chunks, cur_c = [], None

    def flush():
        nonlocal cur_c
        if cur_c:
            for a, b in _split_long(text, cur_c["start"], cur_c["end"], limit):
                chunks.append({"start": a, "end": b, "text": text[a:b], "label": " · ".join(cur_c["titles"][:4])})
        cur_c = None

    for u in units:
        sec = sections[u["sec"]]
        if sec["ref"]:
            flush()
            continue
        if cur_c and ((u["head"] and cur_c["end"] - cur_c["start"] > limit * 0.5) or (u["e"] - cur_c["start"] > limit)):
            flush()
        if not cur_c:
            cur_c = {"start": u["s"], "end": u["e"], "titles": []}
        cur_c["end"] = u["e"]
        if sec["title"] not in cur_c["titles"]:
            cur_c["titles"].append(sec["title"])
    flush()

    abstract = ""
    for sec in sections:
        if re.match(r"^abstract$", sec["title"], re.I):
            abstract = text[sec["start"]:sec["end"]].split("\n\n", 1)[-1]
    if not abstract:
        abstract = text[:1500]

    conclusion = "\n\n".join(
        text[s["start"]:s["end"]]
        for s in sections
        if not s["ref"] and re.match(r"^(conclusions?|discussion|limitations|results and discussion)", s["title"], re.I)
    )[:3500]

    return {
        "sections": [{"title": s["title"], "start": s["start"], "end": s["end"], "ref": s["ref"]} for s in sections],
        "heads": heads,
        "chunks": chunks,
        "abstract": abstract[:1800],
        "conclusion": conclusion,
        "refs_text": refs_text,
        "ref_ranges": ref_ranges,
    }
