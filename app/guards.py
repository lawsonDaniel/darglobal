"""Answer checks that run after the model writes a reply, before the user sees it.

1. Links: every URL must come from the bundled data or from this turn's tool results. Others are removed,
   so the bot cannot send people to invented pages.
2. Phone numbers: only the official company numbers in contacts.json may appear. Any other number is
   replaced, so the bot never shows a personal or invented phone number (even one found on the web).
3. Figures: prices, areas and counts (>= 1,000) must match a number in this turn's evidence, allowing for
   rounding ("2.15M" for 2,150,000) and simple differences or sums of two supported figures in the same
   answer. Unsupported figures trigger one rewrite; if any remain, the reply says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import unquote

from . import tools

URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
PHONE_RE = re.compile(r"(?<![\w/=.,])(?:\+|00)\d[\d\s().-]{6,}\d|(?<![\w/=.,+])0\d{8,11}(?!\d)|(?<![\w/=.,+])800\d{6,8}(?!\d)")
FIG_RE = re.compile(
    r"(?<![\w.,/])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s?(million|mn|billion|bn|thousand|مليون|مليار|ألف)\b|(m|k|b)\b)?(?!\s?%)",
    re.I)
MONEY_CTX = re.compile(r"(sar|sr|riyals?|ريال|ر\.س)\s*$", re.I)
OFFICIAL_ROOTS = {"https://darglobal.co.uk", "https://wasalt.sa", "https://www.darglobal.co.uk", "https://www.wasalt.sa"}
UNIT = {"million": 1e6, "mn": 1e6, "m": 1e6, "مليون": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "مليار": 1e9,
        "thousand": 1e3, "k": 1e3, "ألف": 1e3}


def canon_url(u: str) -> str:
    u = unquote(u.strip()).rstrip(".,;:!?،)»\"'")
    return u[:-1] if u.endswith("/") else u


@lru_cache(maxsize=1)
def _data_urls() -> frozenset[str]:
    return frozenset(canon_url(u) for u in tools.all_known_urls())


@lru_cache(maxsize=1)
def allowed_phone_digits() -> frozenset[str]:
    c = tools.load("contacts")
    nums = [c["darglobal"]["whatsapp"]["number"], c["darglobal"]["phone"]["number"],
            c["wasalt"]["customer_service"]["number"]]
    return frozenset(re.sub(r"\D", "", n) for n in nums)


@dataclass
class Evidence:
    text: str
    urls: set[str] = field(default_factory=set)
    numbers: list[float] = field(default_factory=list)


def build_evidence(texts: list[str]) -> Evidence:
    text = "\n".join(texts)
    urls = set(_data_urls()) | {canon_url(u) for u in URL_RE.findall(text)} | OFFICIAL_ROOTS
    raw = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text) if x.replace(",", "").replace(".", "", 1).isdigit()]
    return Evidence(text, urls, sorted(set(extract_figures(text, evidence=True)) | set(raw)))


def extract_figures(text: str, evidence: bool = False) -> list[float]:
    """Numbers in text, scaled by million/thousand words. In answers, ignores years and small numbers."""
    out = []
    flat = re.sub(r"(?<=\d),(?=\d{3})", ",", text)
    for m in FIG_RE.finditer(flat):
        whole, frac, word, letter = m.groups()
        v = float(whole.replace(",", "") + (frac or ""))
        unit = (word or "").lower() or (letter or "").lower()
        if letter:
            # "2.15M" or "SAR 2m" is money; "15m street" is metres, "5k" is ambiguous: require money context or decimals.
            money = bool(MONEY_CTX.search(flat[max(0, m.start() - 8):m.start()]))
            unit = unit if (frac or money) else ""
        v *= UNIT.get(unit, 1)
        if evidence:
            out.append(v)
            continue
        if v < 1000:
            continue
        if not unit and "," not in whole and not frac and 1900 <= v <= 2100:
            continue  # a year
        out.append(v)
    return out


def _tolerance(raw_value: float) -> float:
    return max(0.6, 0.006 * abs(raw_value))


def _rounding_tolerance(text_fragment: str, value: float) -> float:
    """'2.2M' is stated to the nearest 0.1M, so allow +/-0.05M."""
    m = re.search(r"\.(\d+)\s?(million|mn|m|billion|bn|b|k|thousand|مليون|مليار|ألف)?", text_fragment, re.I)
    if m and m.group(2):
        step = UNIT.get(m.group(2).lower(), 1) / (10 ** len(m.group(1)))
        return max(_tolerance(value), step / 2)
    if m is None and re.search(r"(million|mn|billion|bn|مليون|مليار)|\d[mb]\b", text_fragment, re.I):
        unit = 1e9 if re.search(r"billion|bn|مليار|\db\b", text_fragment, re.I) else 1e6
        return max(_tolerance(value), unit / 2)
    return _tolerance(value)


def unsupported_figures(answer: str, ev: Evidence) -> list[str]:
    import bisect
    nums = ev.numbers
    supported, flagged = [], []
    # Links and phone numbers are checked separately; mask them so their digits are not read as figures.
    answer = PHONE_RE.sub(" ", URL_RE.sub(" ", answer))
    for m in FIG_RE.finditer(answer):
        frag = m.group(0)
        vals = extract_figures(frag)
        if not vals:
            continue
        v = vals[0]
        tol = _rounding_tolerance(frag, v)
        i = bisect.bisect_left(nums, v - tol)
        if i < len(nums) and nums[i] <= v + tol:
            supported.append(v)
        else:
            flagged.append((frag.strip(), v, tol))
    still = []
    for frag, v, tol in flagged:
        derived = any(abs(abs(a - b) - v) <= tol or abs(a + b - v) <= tol
                      for i, a in enumerate(supported) for b in supported[i + 1:])
        if not derived:
            still.append(frag)
    return still


def clean_links(answer: str, ev: Evidence) -> tuple[str, list[str]]:
    removed: list[str] = []

    def md(m: re.Match) -> str:
        if canon_url(m.group(2)) in ev.urls:
            return m.group(0)
        removed.append(m.group(2))
        return m.group(1)
    answer = MD_LINK_RE.sub(md, answer)

    def bare(m: re.Match) -> str:
        u = m.group(0)
        trail = ""
        while u and u[-1] in ".,;:!?،":
            trail, u = u[-1] + trail, u[:-1]
        if canon_url(u) in ev.urls:
            return m.group(0)
        removed.append(u)
        return "[link removed]" + trail
    # Only bare URLs outside markdown links (those were handled above).
    parts = re.split(r"(\[[^\]]+\]\(https?://[^)\s]+\))", answer)
    answer = "".join(p if p.startswith("[") and "](" in p else URL_RE.sub(bare, p) for p in parts)
    return answer, removed


def clean_phones(answer: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    allowed = allowed_phone_digits()

    def sub(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if digits.startswith("00"):
            digits = digits[2:]
        if digits in allowed:
            return m.group(0)
        removed.append(m.group(0))
        return "[number removed]"
    return PHONE_RE.sub(sub, answer), removed


@dataclass
class Report:
    answer: str
    links_removed: list[str]
    phones_removed: list[str]
    unsupported: list[str]


def verify(answer: str, ev: Evidence) -> Report:
    answer, links = clean_links(answer, ev)
    answer, phones = clean_phones(answer)
    return Report(answer, links, phones, unsupported_figures(answer, ev))
