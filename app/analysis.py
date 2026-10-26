import difflib
import re

from . import citations, config, llm, parse, prompts

SEV = {"critical": 0, "major": 1, "minor": 2}
CATS = {"methodology", "statistics", "logic", "claims", "data", "reproducibility", "citations", "ethics", "clarity"}
RECS = {"accept", "minor revision", "major revision", "reject"}


def locate(quote, folded, lo=0, hi=None):
    hi = len(folded) if hi is None else hi
    q = parse.fold(str(quote)).strip().strip("\"'.\u2026 ")
    words = q.split()
    if len(words) < 4:
        return None
    seg = folded[lo:hi]
    m = re.search(r"\s+".join(re.escape(w) for w in words), seg, re.I)
    if m:
        return lo + m.start(), lo + m.end()
    sm = difflib.SequenceMatcher(None, seg.lower(), q.lower(), autojunk=False)
    b = sm.find_longest_match(0, len(seg), 0, len(q))
    if b.size >= max(25, 0.7 * len(q)):
        return lo + b.a, lo + b.a + b.size
    return None


def collect(data, folded, lo, hi, label):
    items = data.get("findings") if isinstance(data, dict) else data
    out = []
    for it in (items or [])[:8]:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        why = str(it.get("explanation", "")).strip()
        if not title or not why:
            continue
        sev = str(it.get("severity", "")).lower().strip()
        cat = str(it.get("category", "")).lower().strip()
        quote = str(it.get("quote", "")).strip()
        span = locate(quote, folded, lo, hi) or locate(quote, folded)
        out.append({
            "title": title,
            "explanation": why,
            "fix": str(it.get("fix", "")).strip(),
            "severity": sev if sev in SEV else "minor",
            "category": cat if cat in CATS else "logic",
            "quote": quote,
            "span": list(span) if span else None,
            "grounded": span is not None,
            "section": label,
        })
    return out


def overlap(a, b):
    inter = min(a[1], b[1]) - max(a[0], b[0])
    return max(inter, 0) / max(min(a[1] - a[0], b[1] - b[0]), 1)


def dedupe(findings):
    keep = []
    for f in sorted(findings, key=lambda f: (SEV[f["severity"]], not f["grounded"])):
        dup = False
        for k in keep:
            similar = difflib.SequenceMatcher(None, f["title"].lower(), k["title"].lower()).ratio() > 0.8
            same = f["span"] and k["span"] and overlap(f["span"], k["span"]) > 0.5 and f["category"] == k["category"]
            if similar or same:
                dup = True
                break
        if not dup:
            keep.append(f)
    keep.sort(key=lambda f: (not f["grounded"], SEV[f["severity"]], f["span"][0] if f["span"] else 0))
    for i, f in enumerate(keep, 1):
        f["id"] = i
    return keep


def as_list(v):
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def analyze(path, name, online, update):
    text = parse.read_document(path)
    if len(text) < 1200:
        raise ValueError("Not enough text could be extracted. Scanned PDFs need OCR first, which is not included.")
    folded = text.translate(parse.FOLD)
    doc = parse.structure(text, config.CHUNK_CHARS)
    chunks = doc["chunks"]
    n = len(chunks)
    if not n:
        raise ValueError("Could not find any body text to analyse.")

    total = 1 + (n if n > 1 else 0) + 1 + n + (1 if n > 1 else 0) + 1
    done = [0]

    def step(stage, msg):
        update(stage, done[0] / total, msg)

    def finish():
        done[0] += 1

    step("cites", "Parsing references and checking in-text citations" + (" against Crossref" if online else ""))
    cites = citations.analyze(text, doc, online, config.CROSSREF_MAILTO)
    finish()

    digests = []
    if n > 1:
        for i, ch in enumerate(chunks, 1):
            step("digest", f"Digesting part {i}/{n}: {ch['label']}")
            digests.append(f"[{ch['label']}] " + llm.chat(prompts.NOTETAKER, prompts.digest(ch["label"], ch["text"]), 400))
            finish()

    step("summary", "Writing the summary")
    if n > 1:
        body, is_digest = "\n\n".join(digests), True
    else:
        body, is_digest = chunks[0]["text"], False
    s = llm.chat_json(prompts.REVIEWER, prompts.summary(doc["abstract"], body, is_digest)) or {}
    summary = {
        "title": str(s.get("title", "")).strip() or name,
        "tldr": str(s.get("tldr", "")).strip(),
        "research_question": str(s.get("research_question", "")).strip(),
        "approach": str(s.get("approach", "")).strip(),
        "key_findings": as_list(s.get("key_findings")),
        "contributions": as_list(s.get("contributions")),
        "stated_limitations": as_list(s.get("stated_limitations")),
        "keywords": as_list(s.get("keywords")),
    }
    finish()

    found = []
    for i, ch in enumerate(chunks, 1):
        step("review", f"Reviewing part {i}/{n}: {ch['label']}")
        data = llm.chat_json(prompts.REVIEWER, prompts.critique(doc["abstract"], ch["label"], ch["text"]))
        found += collect(data, folded, ch["start"], ch["end"], ch["label"])
        finish()

    if n > 1:
        step("global", "Cross-checking claims against evidence across sections")
        data = llm.chat_json(prompts.REVIEWER, prompts.cross_check(doc["abstract"], doc["conclusion"], "\n\n".join(digests)))
        found += collect(data, folded, 0, len(folded), "Whole paper")
        finish()

    findings = dedupe(found)

    step("verdict", "Forming the overall assessment")
    listing = "\n".join(f"#{f['id']} [{f['severity']}] {f['category']}: {f['title']}" for f in findings[:40] if f["grounded"]) or "(no confirmed findings)"
    v = llm.chat_json(prompts.REVIEWER, prompts.verdict(summary["tldr"] or summary["research_question"], listing)) or {}
    crit = sum(1 for f in findings if f["grounded"] and f["severity"] == "critical")
    major = sum(1 for f in findings if f["grounded"] and f["severity"] == "major")
    rec = str(v.get("recommendation", "")).lower().strip()
    if rec not in RECS:
        rec = "major revision" if crit or major > 2 else "minor revision"
    review = {
        "overall": str(v.get("overall_assessment", "")).strip(),
        "strengths": as_list(v.get("strengths")),
        "priorities": as_list(v.get("priority_fixes")),
        "recommendation": rec,
        "findings": findings,
    }
    finish()
    update("done", 1.0, "Done")

    return {
        "meta": {
            "filename": name,
            "words": len(text.split()),
            "parts": n,
            "model": config.MODEL_ID,
            "heads": doc["heads"],
            "sections": [s for s in doc["sections"]],
        },
        "text": text,
        "summary": summary,
        "review": review,
        "citations": cites,
    }
