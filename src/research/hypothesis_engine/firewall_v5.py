r"""Intent-aware numerical-authority firewall (`firewall_v5`). §4.

WHAT V5A.2 ACTUALLY DID, AND WHY IT IS NOT REPAIRABLE BY LOOSENING A RULE
--------------------------------------------------------------------------
Both V5A.2 research-arm responses were rejected WHOLE on one token:

    $.hypotheses[8].question   matched '50%'
        "Does AWAY_TEAM's possession dominance (ALL_PRIOR mean well above 50%) translate
         into a proportionally higher final_third_entries rate ..."

Twelve hypotheses and eighty-eight evidence references were discarded unread, twice. The
diagnosis in the V5A.2 report is exact: the rule is `firewall_v2`'s CLASS_B
(EVIDENCE_VALUE_REPRODUCTION), it predates V5A.2, it was correctly applied, and the model
did write the number.

The naive fix -- stop blocking class B -- is wrong, and §4 says so. Class B is decided by
whether the literal RESOLVES against a packet value, and resolution is the wrong
discriminator in BOTH directions:

    "+0.6 corner advantage"          §4: FORBIDDEN.  If any packet evidence value is
                                     within half an ulp of 0.6, `_classify_prose_match`
                                     returns CLASS_B. A resolution-only allowance passes an
                                     effect size.

    "recorded 60% possession in the  §4: ALLOWED.    `_resolves` gives a BARE INTEGER a
     cited historical cohort"        tolerance of 0.05, so against a true 60.3 the literal
                                     does not resolve and the mandate's own allowed example
                                     is classified CLASS_A and blocked.

So V6 classifies on the FRAME the number sits in -- the words around it and the field it
was written into -- exactly as §4 asks ("structural field context plus lexical rules").
Resolution is retained, but demoted: it is a NECESSARY condition for an allowance, never a
sufficient one, and it is never consulted at all when a predictive marker is present.

THE THREE-STEP DECISION, IN THIS ORDER
--------------------------------------
    1  DENY   a predictive/target marker anywhere in the sentence carrying the number.
              Evaluated FIRST and unconditionally, so "+0.6 corner advantage" cannot be
              rescued by a coincidental resolution.
    2  ALLOW  a historical marker AND every literal resolves against something the packet
              actually supplied (an evidence value at its own written precision, or a
              sample count) AND the FIELD's contract permits a reproduced value.
    3  DENY   everything else. §4: "All rules must remain conservative." An unframed number
              is not given the benefit of the doubt.

FIELD CONTRACT (the "structural field context" half)
-----------------------------------------------------
    evidence_summary   may reproduce a packet-supplied value under the frame contract.
                       Policed MORE strictly than `question` in one respect: EVERY numeric
                       literal must be framed and resolved, not merely those a legacy
                       pattern happens to match. Handing the model a channel for numbers
                       and then not watching it would be worse than not handing it one.
    question           the research question. A predictive number rejects the hypothesis; a
                       reproduced historical value ALSO rejects the hypothesis, because the
                       question is where the model states what to measure and a number
                       belongs in the evidence field or in an evidence id. §4 says a copied
                       value "must not automatically destroy an otherwise valid RESPONSE" --
                       and under V6 it never does: the blast radius is one hypothesis.

DETECTION IS A STRICT SUPERSET OF `firewall_v4`
------------------------------------------------
Every pattern in `firewall._COMPILED` and `firewall_v4._COMPILED` is applied unchanged, to
both prose fields. Nothing is removed. What changes is the DISPOSITION of a finding, and
only in the one direction §4 authorises: a historically framed, packet-resolved value in
`evidence_summary`. `test_firewall_v5_denies_everything_v4_denied_in_question` holds the
line for the field V5A.2 actually used.

`firewall.py`, `firewall_v2.py`, `firewall_v3.py` and `firewall_v4.py` are NOT edited --
their hashes are in the frozen V2/V3/V5A/V5A.1/V5A.2 preregistrations.

ZERO SPEND.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import firewall, firewall_v2, firewall_v4

FIREWALL_VERSION = "firewall_v5"

# ----------------------------------------------------------------------------------------
# Intent labels. These are the two §4 names, plus the conservative default and the
# instrumentation-error label inherited from `firewall_v2`.
# ----------------------------------------------------------------------------------------
INTENT_PREDICTIVE = "MODEL_AUTHORED_PREDICTIVE_QUANTIFICATION"
INTENT_EVIDENCE = "EVIDENCE_VALUE_REPRODUCTION"
INTENT_UNFRAMED = "UNFRAMED_NUMERIC"
INTENT_METRIC_LEXICAL = "METRIC_LEXICAL"

INTENTS = (INTENT_PREDICTIVE, INTENT_EVIDENCE, INTENT_UNFRAMED, INTENT_METRIC_LEXICAL)

# ----------------------------------------------------------------------------------------
# Step 1 -- predictive / target markers. Searched on the METRIC-MASKED sentence, so
# `big_chances` cannot supply the word "chance" and `total_shots` cannot supply "shot".
#
# Each entry is a claim ABOUT THE UPCOMING FIXTURE or about a predictive magnitude. None of
# them can describe a historical observation, which is what makes the list safe to treat as
# an unconditional veto.
# ----------------------------------------------------------------------------------------
_PREDICTIVE_MARKERS: tuple = (
    # explicit probability / market vocabulary
    r"\bprobabilit\w*\b",
    r"\blikelihood\b",
    r"\bchances?\b",
    r"\bodds\b",
    r"\bfair\s+(?:odds|price|probability|value)\b",
    r"\bimplied\b",
    r"\bexpected\s+value\b",
    r"\bEV\b",
    r"\bedge\b",
    r"\boverlay\b",
    r"\bvalue\s+bet\b",
    r"\b(?:stake|bankroll|kelly|unit\s+size|bet\s+size)\b",
    r"\bmarket\b",
    r"\bprice[sd]?\b",
    # advantage / grading vocabulary -- the legacy latent-state error in prose form
    r"\badvantage\b",
    r"\bsuperiority\b",
    r"\bstrength\s+(?:score|rating|grade)\b",
    r"\bmatchup\s+score\b",
    # forward-looking verbs and modal quantification
    r"\b(?:will|would|should|shall)\s+\w*\s*(?:increase|decrease|raise|lower|add|"
    r"reduce|gain|lose|produce|generate|concede|exceed|outperform)\b",
    r"\b(?:expect|predict|project|forecast|anticipate|estimat)\w*\b",
    r"\b(?:gives?|giving|confers?|yields?)\b",
    r"\btranslates?\s+into\b",
    r"\bimplies\b",
    r"\b(?:more|less)\s+likely\b",
    r"\bin\s+(?:this|the\s+upcoming|the\s+target)\s+(?:fixture|match|game)\b",
    r"\bupcoming\s+(?:fixture|match|game)\b",
    # an adjustment expressed as a delta to something
    r"\b(?:increase|decrease|boost|uplift|swing|adjust\w*)\s+\w{0,12}\s*by\b",
    r"\bpercentage[ -]points?\b",
    r"\bpp\b",
)

_PREDICTIVE_RX = tuple(re.compile(p, re.IGNORECASE) for p in _PREDICTIVE_MARKERS)

# ----------------------------------------------------------------------------------------
# Step 2 -- historical markers. A number is a REPRODUCTION only if the prose says, in one
# of these ways, that it is describing something already observed.
# ----------------------------------------------------------------------------------------
_HISTORICAL_MARKERS: tuple = (
    r"\brecord(?:ed|s)?\b",
    r"\bobserv(?:ed|ation\w*)\b",
    r"\bmeasured\b",
    r"\blogged\b",
    r"\bcit(?:ed|ing|ation\w*)\b",
    r"\breferenced\b",
    r"\bhistoric(?:al|ally)?\b",
    r"\bprior\b",
    r"\bpast\b",
    r"\bprevious(?:ly)?\b",
    r"\bcohort\b",
    r"\bsample\b",
    r"\bevidence\b",
    r"\bpacket\b",
    r"\bsupplied\b",
    r"\bacross\s+(?:the|its|their)\b",
    r"\bover\s+(?:the|its|their)\s+last\b",
    r"\bin\s+the\s+(?:cited|supplied|available|exposed)\b",
    r"\b(?:mean|average)\b",
    r"\bALL_PRIOR\b",
    r"\bW5\b",
    r"\bW10\b",
    r"\bHOME_ONLY\b",
    r"\bAWAY_ONLY\b",
    r"\bto\s+date\b",
    r"\bso\s+far\b",
    # Past-tense reporting verbs. Safe to include however common they are: step 1 vetoes
    # unconditionally, so widening this list can never let a predictive claim through --
    # it only reduces how often a plainly retrospective sentence hits the conservative
    # default. Resolution is still required, so "shots were 12" against a packet with no
    # 12 in it is still denied.
    r"\b(?:was|were|had|has|have)\b",
    r"\baverag(?:e[ds]?|ing)\b",
    r"\b(?:posted|registered|tallied|produced|conceded|generated|allowed)\b",
    r"\bN\s*=\s*\d",
    r"\bn\s*=\s*\d",
)

_HISTORICAL_RX = tuple(re.compile(p, re.IGNORECASE) for p in _HISTORICAL_MARKERS)

#: An explicit sample-count form. Its literal is checked against the packet's sample_n
#: values rather than its evidence values, because `firewall_v2.evidence_values`
#: deliberately excludes sample counts and widening THAT would change a frozen module's
#: meaning.
_SAMPLE_N_RX = re.compile(r"\b(?:N|n|sample(?:\s+size)?(?:\s+of)?)\s*[=:]?\s*(\d+)\b")

_NUM_RX = re.compile(r"\d+(?:\.\d+)?")

#: Bare integers that are structural rather than quantitative, and are never a claim:
#: window lengths, back-line counts, formation digits. A literal matching one of these
#: SHAPES still has to be framed; this only spares it the resolution requirement.
_STRUCTURAL_NUMERIC_RX = (
    re.compile(r"\blast\s+\d{1,2}\b", re.IGNORECASE),
    re.compile(r"\bW\d{1,2}\b"),
    re.compile(r"\bback[\s-]?(?:three|four|five|3|4|5)\b", re.IGNORECASE),
    re.compile(r"\b\d\s*-\s*\d\s*-\s*\d(?:\s*-\s*\d)?\b"),
)


def _sentences(text: str) -> list:
    """Split on sentence enders, keeping the offsets so a match maps back to its sentence.

    Deliberately crude and deterministic. A sentence boundary the splitter misses only
    WIDENS the window the predictive markers are searched in, which errs toward denial.
    """
    out, start = [], 0
    for m in re.finditer(r"[.;!?]\s+|\n", text or ""):
        out.append((start, m.end(), (text or "")[start:m.end()]))
        start = m.end()
    tail = (text or "")[start:]
    if tail:
        out.append((start, len(text or ""), tail))
    return out or [(0, len(text or ""), text or "")]


def _sentence_for(text: str, pos: int) -> str:
    for a, b, s in _sentences(text):
        if a <= pos < b:
            return s
    return text or ""


def predictive_markers_in(text: str) -> list:
    """Predictive markers present in METRIC-MASKED prose. Sorted, deterministic."""
    masked = firewall_v2.mask_metric_lexicon(text or "")
    found = set()
    for rx in _PREDICTIVE_RX:
        m = rx.search(masked)
        if m:
            found.add(m.group(0).strip().lower())
    return sorted(found)


def historical_markers_in(text: str) -> list:
    masked = firewall_v2.mask_metric_lexicon(text or "")
    found = set()
    for rx in _HISTORICAL_RX:
        m = rx.search(masked)
        if m:
            found.add(m.group(0).strip().lower())
    return sorted(found)


def sample_n_values(packet: Optional[dict]) -> tuple:
    """Every sample count the packet supplied, from evidence records and summary rows.

    Separate from `firewall_v2.evidence_values` on purpose: that function excludes
    `sample_n` by design and is frozen. A sample count is legitimate structural metadata
    (§4 lists "N=18" as ALLOWED), so V6 resolves it against its own source.
    """
    if not packet:
        return ()
    out: set = set()
    for item in packet.get("evidence") or []:
        if isinstance(item, dict):
            n = item.get("sample_n")
            if isinstance(n, int) and not isinstance(n, bool):
                out.add(n)
    for sec in packet.get("sections") or []:
        cols = sec.get("columns") or []
        if "sample_n" in cols:
            i = cols.index("sample_n")
            for row in sec.get("rows") or []:
                if len(row) > i and isinstance(row[i], int) \
                        and not isinstance(row[i], bool):
                    out.add(row[i])
        for blk in sec.get("blocks") or []:
            bcols = blk.get("columns") or []
            if "sample_n" in bcols:
                j = bcols.index("sample_n")
                for row in blk.get("rows") or []:
                    if isinstance(row, list) and len(row) > j \
                            and isinstance(row[j], int) and not isinstance(row[j], bool):
                        out.add(row[j])
        for rec in sec.get("records") or []:
            if isinstance(rec, dict):
                n = rec.get("sample_n")
                if isinstance(n, int) and not isinstance(n, bool):
                    out.add(n)
    return tuple(sorted(out))


def resolves_at_written_precision(literal: str, values: tuple) -> bool:
    """Does a literal match a supplied value AT THE PRECISION THE MODEL WROTE IT?

    `firewall_v2._resolves` gives a bare integer a tolerance of 0.05, so "60" does not
    resolve against 60.3 and §4's own ALLOWED example would be blocked. That tolerance
    exists in v2 for a reason -- it stops "below 50%", a domain constant a model can write
    with no evidence at all, being mislabelled as a copied value -- but under V6 the frame
    already carries that discrimination: an unframed "below 50%" is denied at step 3
    whatever this function says, and a PREDICTIVE "50% chance" is denied at step 1 before
    this function is reached.

    So V6 resolves at the literal's own precision in BOTH directions: "60" covers
    [59.5, 60.5), "44.6" covers [44.55, 44.65). That is what "the model rounded a value it
    was given" actually means. The stricter v2 rule is retained alongside and reported as
    `resolved_exactly`, so an audit can always tell a rounded citation from an exact one.
    """
    try:
        x = float(literal)
    except ValueError:
        return False
    nd = len(literal.split(".")[1]) if "." in literal else 0
    tol = 0.5 * (10.0 ** -nd)
    return any(abs(v - x) < tol for v in values)


@dataclass(frozen=True)
class IntentFinding:
    """One numeric literal, classified by intent and disposed of by field contract."""
    path: str
    field: str
    kind: str
    matched: str
    intent: str
    blocking: bool
    detail: str
    predictive_markers: tuple = ()
    historical_markers: tuple = ()
    resolved: bool = False
    resolved_exactly: bool = False

    def to_dict(self) -> dict:
        return {"path": self.path, "field": self.field, "kind": self.kind,
                "matched": self.matched, "intent": self.intent,
                "blocking": self.blocking, "detail": self.detail,
                "predictive_markers": list(self.predictive_markers),
                "historical_markers": list(self.historical_markers),
                "resolved": self.resolved, "resolved_exactly": self.resolved_exactly}

    def __str__(self) -> str:
        return f"[{self.intent}] {self.path}: {self.kind} -- {self.detail}"


def classify_fragment(fragment: str, sentence: str, *, values: tuple, sample_ns: tuple):
    """The three-step decision, for ONE matched fragment in ONE sentence.

    Returns `(intent, predictive, historical, resolved, resolved_exactly)`. Field policy is
    NOT applied here: intent is a property of the prose, disposition is a property of the
    field, and keeping them apart is what lets the same sentence be allowed in
    `evidence_summary` and rejected in `question` without two classifiers.
    """
    predictive = tuple(predictive_markers_in(sentence))
    historical = tuple(historical_markers_in(sentence))
    lits = tuple(_NUM_RX.findall(fragment or ""))

    # ---- step 1: unconditional veto ---------------------------------------------------
    if predictive:
        return INTENT_PREDICTIVE, predictive, historical, False, False

    # ---- a match with no number at all, explained entirely by a metric name ------------
    if not lits:
        masked = firewall_v2.mask_metric_lexicon(fragment or "")
        if masked != (fragment or ""):
            return INTENT_METRIC_LEXICAL, predictive, historical, False, False
        return INTENT_UNFRAMED, predictive, historical, False, False

    # ---- step 2: historical frame + resolution ----------------------------------------
    sample_hit = _SAMPLE_N_RX.search(fragment or "") or _SAMPLE_N_RX.search(sentence or "")
    resolved = all(
        resolves_at_written_precision(l, values)
        or (sample_hit is not None and resolves_at_written_precision(l, tuple(
            float(v) for v in sample_ns)))
        for l in lits)
    resolved_exactly = bool(values) and all(
        firewall_v2._resolves(l, values) for l in lits)
    if historical and resolved:
        return INTENT_EVIDENCE, predictive, historical, True, resolved_exactly

    # ---- step 3: conservative default -------------------------------------------------
    return INTENT_UNFRAMED, predictive, historical, resolved, resolved_exactly


_ALL_PATTERNS = firewall._COMPILED + firewall_v4._COMPILED


def _structural(fragment: str, sentence: str) -> bool:
    return any(rx.search(fragment) or rx.search(sentence) for rx in _STRUCTURAL_NUMERIC_RX)


def scan_prose_field(text: str, path: str, field: str, *, values: tuple, sample_ns: tuple,
                     evidence_bearing: bool) -> list:
    """Every finding for ONE prose field of ONE hypothesis.

    `evidence_bearing` selects the field contract:

        True   (`evidence_summary`)  every numeric literal is examined, and an
                                     EVIDENCE_VALUE_REPRODUCTION is ALLOWED.
        False  (`question`)          the frozen pattern set decides what is examined, and
                                     nothing numeric is allowed; the intent label still
                                     records WHICH kind of violation it was.
    """
    raw = text or ""
    masked = firewall_v2.mask_metric_lexicon(raw)
    out: list = []
    seen: set = set()

    for rx, label in _ALL_PATTERNS:
        raw_m = rx.search(raw)
        if not raw_m:
            continue
        masked_m = rx.search(masked)
        # `firewall_v2`'s CLASS_C rule, reused verbatim in substance: a match that carries
        # NO number and DISAPPEARS once approved metric names are masked existed only
        # because a metric name supplied the trigger vocabulary. "Does the home team
        # generate more big chances at home ..." trips `probability_claim` on the substring
        # "chances at" and is not a probability claim. Instrumentation error, suppressed.
        # Decided against the masked FULL TEXT, not the fragment -- bare "chances" is not
        # itself a metric name, so masking the fragment alone would never clear it.
        if not masked_m and not _NUM_RX.findall(raw_m.group(0)):
            key = (label, raw_m.group(0))
            if key in seen:
                continue
            seen.add(key)
            out.append(IntentFinding(
                path, field, label, raw_m.group(0), INTENT_METRIC_LEXICAL, False,
                "the match carries no number and is entirely explained by an approved "
                "metric name from the capability inventory; suppressed as instrumentation "
                "error", (), (), False, False))
            continue
        # A match containing a NUMERIC LITERAL is never metric-lexical, even when a metric
        # name is what let the pattern anchor: "+0.6 corners" is an effect size whether or
        # not `corners` is approved. Classified on the effective match, as v2 does.
        effective = masked_m or raw_m
        frag = effective.group(0)
        sentence = _sentence_for(raw, raw_m.start())
        intent, pred, hist, res, exact = classify_fragment(
            frag, sentence, values=values, sample_ns=sample_ns)
        key = (label, frag)
        if key in seen:
            continue
        seen.add(key)
        blocking = not (evidence_bearing and intent == INTENT_EVIDENCE)
        out.append(IntentFinding(
            path, field, label, frag, intent, blocking,
            _detail(intent, field, evidence_bearing, pred), pred, hist, res, exact))

    if not evidence_bearing:
        return out

    # The evidence-bearing field is policed literal-by-literal, not pattern-by-pattern.
    # A channel for numbers that only inspects the numbers a legacy regex happens to
    # notice is not a policed channel.
    for m in _NUM_RX.finditer(raw):
        frag = m.group(0)
        sentence = _sentence_for(raw, m.start())
        if _structural(frag, sentence):
            continue
        intent, pred, hist, res, exact = classify_fragment(
            frag, sentence, values=values, sample_ns=sample_ns)
        if intent == INTENT_EVIDENCE:
            continue
        key = ("bare_literal", frag)
        if key in seen:
            continue
        seen.add(key)
        out.append(IntentFinding(
            path, field, "bare_literal", frag, intent, True,
            _detail(intent, field, evidence_bearing, pred), pred, hist, res, exact))
    return out


def _detail(intent: str, field: str, evidence_bearing: bool, pred: tuple) -> str:
    if intent == INTENT_PREDICTIVE:
        return (f"model-authored predictive quantification in {field!r}: the sentence "
                f"carries {list(pred)}, which makes the number a claim about the upcoming "
                f"fixture or about a predictive magnitude. The deterministic engine owns "
                f"every such number; no field and no phrasing makes one admissible.")
    if intent == INTENT_EVIDENCE and not evidence_bearing:
        return (f"a value the packet supplied, reproduced in {field!r}. The value itself "
                f"is legitimate -- it is the FIELD that is wrong. Cite the evidence id, or "
                f"put the reproduced value in `evidence_summary`, where the contract "
                f"permits it. This rejects THIS hypothesis only.")
    return (f"unframed numeric literal in {field!r}: nothing in the sentence says this is "
            f"a value the packet supplied, and it does not resolve against one. A number "
            f"with no historical frame is treated as authored, conservatively.")


def scan_hypothesis(h: dict, index: int, *, packet=None, values=None,
                    sample_ns=None) -> list:
    """Every firewall finding for ONE hypothesis.

    Scans the hypothesis in isolation -- `firewall_v3.scan` and `firewall_v4.scan` walk the
    WHOLE payload, which is exactly why a violation in one hypothesis could reach a
    response-level verdict. Structural layers (`scan_numerical_authority`,
    `scan_latent_grading`) are applied to the hypothesis object alone; the numeric-field
    half of the first is owned by `v6_numeric_contract` and is not duplicated here.
    """
    from src.research.hypothesis_oos import v6_numeric_contract as NC
    ev = tuple(values) if values is not None else firewall_v2.evidence_values(packet)
    sns = tuple(sample_ns) if sample_ns is not None else sample_n_values(packet)
    out: list = []

    for v in firewall.scan_latent_grading(h):
        out.append(IntentFinding(
            f"$.hypotheses[{index}]{v.path[1:]}", v.path.rsplit(".", 1)[-1], v.kind,
            str(v.detail)[:120], INTENT_PREDICTIVE, True,
            f"latent grading: {v.detail}", ("latent_grade",), (), False, False))

    for field in NC.PROSE_FIELDS:
        text = h.get(field)
        if not isinstance(text, str):
            continue
        out.extend(scan_prose_field(
            text, f"$.hypotheses[{index}].{field}", field,
            values=ev, sample_ns=sns,
            evidence_bearing=field in NC.EVIDENCE_BEARING_PROSE_FIELDS))
    return out


def blocking(findings) -> list:
    return [f for f in findings if f.blocking]


def suppressed(findings) -> list:
    return [f for f in findings if not f.blocking]


def intent_counts(findings) -> dict:
    counts = {i: 0 for i in INTENTS}
    for f in findings:
        counts[f.intent] = counts.get(f.intent, 0) + 1
    return counts


def version_stamp() -> dict:
    return {"firewall_version": FIREWALL_VERSION,
            "detection_superset_of": firewall_v4.FIREWALL_VERSION,
            "n_patterns_inherited": len(_ALL_PATTERNS),
            "n_predictive_markers": len(_PREDICTIVE_MARKERS),
            "n_historical_markers": len(_HISTORICAL_MARKERS),
            "intents": list(INTENTS),
            "decision_order": ["1 DENY on any predictive marker (unconditional)",
                               "2 ALLOW on historical marker + resolution + field permits",
                               "3 DENY otherwise (conservative default)"],
            "resolution_is_necessary_not_sufficient": True}
