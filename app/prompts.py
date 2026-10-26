REVIEWER = (
    "You are a meticulous senior peer reviewer with deep expertise in research methodology, statistics and "
    "scientific writing. You judge only what the supplied text supports, never invent details, and never "
    "criticise without evidence from the text. Answer with one valid JSON object and nothing else."
)

NOTETAKER = "You are a precise scientific note-taker. You report only what the text states. No opinions."

FINDING_SCHEMA = (
    '{"findings":[{"category":"methodology|statistics|logic|claims|data|reproducibility|citations|ethics|clarity",'
    '"severity":"critical|major|minor","title":"max 12 words","quote":"verbatim excerpt","explanation":"1-3 sentences",'
    '"fix":"specific remedy"}]}'
)

RULES = (
    "Rules:\n"
    "- Each finding needs a \"quote\": an exact, verbatim excerpt (8-40 words) from the supplied text that the problem is anchored to.\n"
    "- Do not report something the supplied text itself resolves. Do not speculate about parts you cannot see.\n"
    "- Prefer a few well-justified findings over many weak ones (at most 6). Return an empty list if the text is sound.\n"
    "- severity: critical = invalidates a main conclusion; major = materially weakens it; minor = clarity or polish.\n"
    "- \"fix\" must be concrete and actionable (what to run, change, add or rewrite), never generic advice.\n"
)

LOOK_FOR = (
    "unsupported or overstated claims; causal language from correlational evidence; logical gaps and non sequiturs; "
    "sampling, selection and confounding problems; missing baselines, controls or ablations; train/test leakage; "
    "inappropriate statistical tests, missing effect sizes or confidence intervals, multiple comparisons, small samples; "
    "internal inconsistencies in numbers or definitions; reproducibility gaps (data, code, hyperparameters, versions); "
    "ethical or consent gaps; strong factual claims with no citation"
)


def critique(abstract, label, passage):
    return (
        f"Paper abstract (context only):\n{abstract}\n\nSection(s) under review: {label}\n\n"
        f"Passage:\n\"\"\"\n{passage}\n\"\"\"\n\n"
        f"Identify genuine weaknesses in this passage. Look for: {LOOK_FOR}.\n\n{RULES}\n"
        f"Return JSON of this shape:\n{FINDING_SCHEMA}"
    )


def cross_check(abstract, conclusion, digests):
    return (
        f"Abstract (verbatim):\n\"\"\"\n{abstract}\n\"\"\"\n\n"
        f"Discussion / conclusion (verbatim):\n\"\"\"\n{conclusion or '(not found)'}\n\"\"\"\n\n"
        f"Paraphrased notes on every section (do NOT quote from these):\n{digests}\n\n"
        "Find whole-paper problems: claims in the abstract or conclusion that the reported results do not support; "
        "contradictions between sections; a research question that is never actually answered; scope or generalisation "
        "beyond what the design allows; missing limitations; novelty overstated.\n\n"
        "Quotes must be copied verbatim from the abstract or the discussion/conclusion above.\n\n"
        f"{RULES}\nReturn JSON of this shape:\n{FINDING_SCHEMA}"
    )


def digest(label, passage):
    return (
        f"Section(s): {label}\n\"\"\"\n{passage}\n\"\"\"\n\n"
        "Write a dense factual digest (max 150 words): the question, design, data, key numbers, and claims made. Plain prose."
    )


SUMMARY_SCHEMA = (
    '{"title":"paper title","tldr":"max 60 words","research_question":"...","approach":"2-4 sentences",'
    '"key_findings":["..."],"contributions":["..."],"stated_limitations":["..."],"keywords":["..."]}'
)


def summary(abstract, body, is_digest):
    kind = "Section digests" if is_digest else "Full text"
    return (
        f"Abstract:\n{abstract}\n\n{kind}:\n\"\"\"\n{body}\n\"\"\"\n\n"
        "Summarise this paper faithfully for a busy expert. Use only information present above; include concrete numbers "
        "where given. If something is not stated, use an empty list or say \"not stated\".\n"
        f"Return JSON of this shape:\n{SUMMARY_SCHEMA}"
    )


def verdict(tldr, listing):
    return (
        f"Paper in brief: {tldr}\n\nConfirmed findings from the review:\n{listing}\n\n"
        "Write the overall assessment a reviewer would give the editor. Base it only on the findings above and be calibrated: "
        "do not call a paper flawed beyond what the findings show.\n"
        'Return JSON: {"overall_assessment":"3-5 sentences","strengths":["3-5 items, only if evident"],'
        '"priority_fixes":["3-6 ordered, concrete actions"],"recommendation":"accept|minor revision|major revision|reject"}'
    )
