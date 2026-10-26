import difflib
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx

YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
NUM = re.compile(r"\[(\d{1,3}(?:\s*[,\u2013\-]\s*\d{1,3})*)\]")
NAME = r"[A-Z][A-Za-z'\u2019\-]+"
AY = re.compile(rf"(?P<a>{NAME})(?:\s+(?:et al\.?|(?:and|&)\s+{NAME}))?,?\s+(?P<y>(?:19|20)\d{{2}})[a-z]?")
NARR = re.compile(rf"(?P<a>{NAME})(?:\s+(?:et al\.?|(?:and|&)\s+{NAME}))?\s*\((?P<y>(?:19|20)\d{{2}})[a-z]?\)")
PAREN = re.compile(r"\(([^()]{4,300})\)")
SPLIT_AY = re.compile(rf"(?<=[.)\d]\s)(?={NAME},\s(?:[A-Z]\.\s?){{1,3}})")


def split_refs(t):
    t = t.strip()
    if not t:
        return []
    if len(re.findall(r"(?:^|\s)\[\d{1,3}\]\s", t)) >= 3:
        out = []
        for part in re.split(r"(?=(?:^|\s)\[\d{1,3}\]\s)", t):
            m = re.match(r"\s*\[(\d{1,3})\]\s*(.*)", part, re.S)
            if m and len(m.group(2)) > 20:
                out.append((int(m.group(1)), " ".join(m.group(2).split())))
        return out
    pieces = []
    numbered = len(re.findall(r"(?:^|\s)\d{1,3}\.\s+[A-Z]", t)) >= 5
    for p in t.split("\n\n"):
        parts = re.split(r"\s(?=\d{1,3}\.\s+[A-Z])", p) if numbered else [p]
        for q in parts:
            pieces += SPLIT_AY.split(q)
    pieces = [" ".join(p.split()) for p in pieces if len(p.strip()) > 25]
    nums = [re.match(r"^(\d{1,3})[.)]\s+", p) for p in pieces]
    if pieces and sum(1 for m in nums if m) >= 0.6 * len(pieces):
        return [(int(m.group(1)), p[m.end():]) if m else (i + 1, p) for i, (m, p) in enumerate(zip(nums, pieces))]
    return [(i + 1, p) for i, p in enumerate(pieces)]


def parse_refs(refs_text):
    refs = []
    for n, raw in split_refs(refs_text):
        y = YEAR.search(raw)
        d = DOI.search(raw)
        refs.append({
            "n": n,
            "raw": raw,
            "year": int(y.group(1)) if y else None,
            "doi": d.group(0).rstrip(".,;)]") if d else None,
            "cites": 0,
            "flags": [],
            "status": "pending",
            "match": None,
        })
    return refs


def expand(token):
    out = []
    for part in re.split(r"\s*,\s*", token):
        m = re.match(r"(\d+)\s*[\u2013\-]\s*(\d+)$", part)
        if m and 0 < int(m.group(2)) - int(m.group(1)) < 50:
            out += list(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def in_text(masked):
    numeric, author = [], []
    for m in NUM.finditer(masked):
        for n in expand(m.group(1)):
            numeric.append((n, m.start()))
    for m in PAREN.finditer(masked):
        inner = m.group(1)
        if not YEAR.search(inner):
            continue
        for part in inner.split(";"):
            a = AY.search(part)
            if a:
                author.append((a.group("a"), int(a.group("y")), m.start()))
    for m in NARR.finditer(masked):
        author.append((m.group("a"), int(m.group("y")), m.start()))
    return numeric, author


def judge(ref, item):
    title = " ".join(item.get("title") or [""])
    toks = set(re.findall(r"[a-z0-9]{3,}", title.lower()))
    raw = set(re.findall(r"[a-z0-9]{3,}", ref["raw"].lower()))
    score = len(toks & raw) / max(len(toks), 1)
    parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    cy = parts[0][0] if parts and parts[0] else None
    year_ok = ref["year"] is None or cy is None or abs(ref["year"] - cy) <= 1
    if score >= 0.8 and year_ok:
        status = "verified"
    elif ref["doi"] and score < 0.5:
        status = "mismatch"
    elif score >= 0.55:
        status = "mismatch" if not year_ok else "verified"
    else:
        status = "unverified"
    return status, {"title": title, "doi": item.get("DOI"), "year": cy, "score": round(score, 2)}


def verify_one(ref, client):
    try:
        if ref["doi"]:
            r = client.get(f"https://api.crossref.org/works/{ref['doi']}")
            if r.status_code == 200:
                ref["status"], ref["match"] = judge(ref, r.json()["message"])
                if ref["status"] == "mismatch":
                    ref["flags"].append("DOI resolves to a different paper")
                return
        r = client.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": ref["raw"][:300], "rows": 1, "select": "title,issued,DOI"},
        )
        items = r.json().get("message", {}).get("items", []) if r.status_code == 200 else []
        if items:
            ref["status"], ref["match"] = judge(ref, items[0])
        else:
            ref["status"] = "unverified"
    except Exception:
        ref["status"] = "skipped"


def verify_all(refs, mailto):
    ua = f"Marginalia/1.0 (mailto:{mailto})" if mailto else "Marginalia/1.0"
    with httpx.Client(timeout=12, headers={"User-Agent": ua}) as client:
        with ThreadPoolExecutor(6) as ex:
            list(ex.map(lambda r: verify_one(r, client), refs[:80]))
    for r in refs[80:]:
        r["status"] = "skipped"


def analyze(text, doc, online, mailto):
    masked = list(text)
    for a, b in doc["ref_ranges"]:
        masked[a:b] = " " * (b - a)
    masked = "".join(masked)

    refs = parse_refs(doc["refs_text"])
    out = {"found": bool(refs), "style": "unknown", "references": refs, "issues": [], "histogram": [], "stats": {}}
    numeric, author = in_text(masked)

    if not refs:
        out["issues"].append({"type": "missing", "text": "No reference list could be located in this document.", "pos": None})
        out["stats"] = {"references": 0, "in_text": len(numeric) + len(author)}
        return out

    style = "numeric" if len(numeric) >= len(author) else "author-year"
    out["style"] = style
    by_n = {r["n"]: r for r in refs}
    max_n = max(by_n)
    total = 0
    dangling = 0

    if style == "numeric":
        seen = {}
        for n, pos in numeric:
            total += 1
            seen.setdefault(n, pos)
            if n in by_n:
                by_n[n]["cites"] += 1
        for n, pos in sorted(seen.items()):
            if n not in by_n:
                dangling += 1
                out["issues"].append({"type": "dangling", "text": f"Citation [{n}] has no matching entry (the list ends at [{max_n}]).", "pos": pos})
    else:
        seen = {}
        for a, y, pos in author:
            total += 1
            hits = [r for r in refs if r["year"] == y and a.lower() in r["raw"][:150].lower()]
            for r in hits[:1]:
                r["cites"] += 1
            if not hits:
                seen.setdefault((a, y), pos)
        for (a, y), pos in seen.items():
            dangling += 1
            out["issues"].append({"type": "dangling", "text": f"In-text citation “{a} {y}” has no matching reference.", "pos": pos})

    uncited = 0
    for r in refs:
        if r["cites"] == 0:
            uncited += 1
            r["flags"].append("never cited in the text")
            out["issues"].append({"type": "uncited", "text": f"Reference {r['n']} is listed but never cited.", "pos": None})
        if r["year"] is None:
            r["flags"].append("no year found")

    low = [r["raw"][:160].lower() for r in refs]
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            if difflib.SequenceMatcher(None, low[i], low[j]).quick_ratio() > 0.9 and difflib.SequenceMatcher(None, low[i], low[j]).ratio() > 0.92:
                refs[j]["flags"].append(f"possible duplicate of {refs[i]['n']}")
                out["issues"].append({"type": "duplicate", "text": f"References {refs[i]['n']} and {refs[j]['n']} look like duplicates.", "pos": None})

    if online:
        verify_all(refs, mailto)
        for r in refs:
            if r["status"] == "mismatch":
                out["issues"].append({"type": "mismatch", "text": f"Reference {r['n']} does not match the closest bibliographic record.", "pos": None})
    else:
        for r in refs:
            r["status"] = "skipped"

    years = [r["year"] for r in refs if r["year"]]
    now = date.today().year
    counts = Counter(r["status"] for r in refs)
    out["histogram"] = sorted(Counter(years).items())
    out["stats"] = {
        "references": len(refs),
        "in_text": total,
        "dangling": dangling,
        "uncited": uncited,
        "verified": counts["verified"],
        "mismatch": counts["mismatch"],
        "unverified": counts["unverified"],
        "online": online,
        "median_year": int(statistics.median(years)) if years else None,
        "recent_share": round(sum(1 for y in years if y >= now - 5) / len(years), 2) if years else None,
        "oldest": min(years) if years else None,
        "newest": max(years) if years else None,
    }
    return out
