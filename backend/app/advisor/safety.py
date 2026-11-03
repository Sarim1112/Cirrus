"""Privacy masking, topic guardrails and number verification for AI output."""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------------------------
# Masking: applied to anything sent to a model, even a local one, because OLLAMA_URL can be remote.
# ---------------------------------------------------------------------------------------------
_MASKS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "[iban]"),
    (
        re.compile(r"(?<![\d.,$])(?:\+?\d{1,2}[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"),
        "[phone]",
    ),
    (re.compile(r"\b\d{3}[ -]\d{3}[ -]\d{3}\b"), "[id]"),
    (re.compile(r"\b[A-Z]\d[A-Z][ -]?\d[A-Z]\d\b"), "[postcode]"),
    (re.compile(r"(?<![\d.,$])\b\d{7,}\b(?![.,]\d)"), "[number]"),
]


def mask_text(text: str) -> str:
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    return text


def mask_data(value):
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: mask_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_data(v) for v in value]
    return value


# ---------------------------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------------------------
_SELF_HARM = re.compile(
    r"\b(kill myself|end my life|suicid\w*|don'?t want to (live|be here|be alive)|"
    r"better off without me|hurt myself|no reason to live)\b",
    re.IGNORECASE,
)
_ILLEGAL = re.compile(
    r"\b(launder\w*|evade (my )?tax\w*|tax evasion|hide (my |this )?(income|money|cash) from|"
    r"fake (receipt|invoice|pay ?stub)s?|forge\w*|commit fraud|avoid paying (any )?tax\w*)\b",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"(ignore (all |any |your |the )?(previous |prior |above )?(instructions|rules|prompts?)|"
    r"(reveal|show|print|repeat) (me )?(your |the )?(system )?(prompt|instructions)|"
    r"you are now |pretend (you are|to be)|jailbreak|developer mode|"
    r"(other|another) (user|person|customer)'?s? (data|transactions|account|spending))",
    re.IGNORECASE,
)
_INVEST_WORD = (
    r"(stocks?|etfs?|crypto\w*|bitcoin|btc|ethereum|eth|dogecoin|shares?|mutual funds?|"
    r"index funds?|options trading|forex|nvidia|nvda|tesla|tsla|apple stock|s&p|tfsa|rrsp|401k|"
    r"\binvest\w*)"
)
_INVEST = re.compile(
    rf"\b(should i|which|what|best|recommend|buy|sell|worth|put my|good time|how much).{{0,50}}"
    rf"\b{_INVEST_WORD}\b|\b{_INVEST_WORD}\b.{{0,40}}\b(should i|good|worth|recommend|best)\b",
    re.IGNORECASE,
)
_PROFESSIONAL = re.compile(
    r"\b(file my tax\w*|tax return|tax deduction|write.?off|declare bankruptcy|bankruptcy law|"
    r"consumer proposal|sue |lawsuit|legal advice|mortgage rate|should i refinance)\b",
    re.IGNORECASE,
)
_HARDSHIP = re.compile(
    r"\b(can'?t (pay|afford) (my |the )?(rent|bills?|debt|loan|food|groceries)|"
    r"cannot (pay|afford) (my |the )?(rent|bills?|debt|loan|food|groceries)|eviction|evicted|"
    r"in collections|debt collector|drowning in debt|overwhelmed by debt|going bankrupt|"
    r"behind on (my )?(rent|bills?|payments))\b",
    re.IGNORECASE,
)


@dataclass
class GuardDecision:
    kind: str
    reply: str | None = None


def check_message(message: str) -> GuardDecision | None:
    if _SELF_HARM.search(message):
        return GuardDecision(
            "crisis",
            "I'm really glad you said something, and money stress can feel crushing. Please talk "
            "to someone now. In Canada or the US, call or text 988. Elsewhere, your local "
            "emergency number or crisis line can help. If you're in immediate danger, call "
            "emergency services. Your finances can wait, and when you're ready, I'll help you "
            "sort through them one step at a time.",
        )
    if _ILLEGAL.search(message):
        return GuardDecision(
            "illegal",
            "I can't help with that. I can help you find money in your budget for what you owe, "
            "or set aside a monthly amount for taxes.",
        )
    if _INJECTION.search(message):
        return GuardDecision(
            "injection",
            "I can only help with your own budget, and I can't share my instructions. Try asking "
            "where your money went last month.",
        )
    if _INVEST.search(message):
        return GuardDecision("investing")
    if _PROFESSIONAL.search(message):
        return GuardDecision(
            "professional",
            "That needs someone who can review your full situation, such as an accountant, a "
            "lawyer or a licensed advisor. I can pull together your spending and income summary "
            "to bring to that conversation.",
        )
    if _HARDSHIP.search(message):
        return GuardDecision("hardship")
    return None


_OUTPUT_ADVICE = re.compile(
    r"\b(you should|i recommend|i'd recommend|consider) (buy|buying|sell|selling|invest\w*)\b.{0,40}"
    rf"\b{_INVEST_WORD}\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------------------------
# Number verification: every figure in a model's reply must come from the calculation tools.
# ---------------------------------------------------------------------------------------------
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?(%|percent\b)?")
_CURRENCY_BEFORE = re.compile(r"(?:[$€£]|[A-Z]{3}\s?)-?\s?$")
_SPELLED = re.compile(
    r"\b(?:hundred|thousand|million)s? of dollars\b|\b(?:one|two|three|four|five|six|seven|eight|"
    r"nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ]?(?:\w+ )?"
    r"(?:hundred|thousand|million|dollars|bucks|percent)\b",
    re.IGNORECASE,
)


def _as_float(whole: str, fraction: str | None) -> float:
    return float(whole.replace(",", "") + (fraction or ""))


def numbers_in_text(text: str) -> set[float]:
    return {_as_float(m.group(1), m.group(2)) for m in _NUMBER.finditer(text)}


def allowed_numbers(*sources) -> set[float]:
    """Collect every figure a reply may cite from tool data, drafts and the user's own message."""
    allowed: set[float] = set()

    def walk(value, key=""):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            if key.endswith("_cents"):
                allowed.add(round(abs(value) / 100, 2))
            else:
                allowed.add(abs(float(value)))
        elif isinstance(value, str):
            allowed.update(numbers_in_text(value))
        elif isinstance(value, dict):
            for k, v in value.items():
                if not (isinstance(k, str) and (k.endswith("_ids") or k == "id")):
                    walk(v, str(k))
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item, key)

    for source in sources:
        walk(source)
    return allowed


def _is_allowed(value: float, allowed: set[float]) -> bool:
    for candidate in allowed:
        if abs(candidate - value) < 0.006:
            return True
        # Rounding a real figure to whole dollars is fine: $412.60 can be "$413" or "about $413".
        if float(value).is_integer() and abs(round(candidate) - value) < 0.001:
            return True
    return False


@dataclass
class Verification:
    ok: bool
    unverified: list[str]
    reason: str = ""


def verify_reply(
    reply: str, allowed: set[float], required: list[float] | None = None
) -> Verification:
    bad = []
    if _OUTPUT_ADVICE.search(reply):
        return Verification(False, [], "investment recommendation")
    spelled = _SPELLED.search(reply)
    if spelled:
        return Verification(False, [spelled.group(0)], "spelled-out amount")
    for match in _NUMBER.finditer(reply):
        value = _as_float(match.group(1), match.group(2))
        has_money = bool(_CURRENCY_BEFORE.search(reply[: match.start()]))
        has_percent = bool(match.group(3))
        plain_int = match.group(2) is None and "," not in match.group(1)
        if not has_money and not has_percent and plain_int:
            # Small counts, days of the month and years aren't financial claims.
            if value <= 31 or 2000 <= value <= 2100:
                continue
        if not _is_allowed(value, allowed):
            bad.append(match.group(0).strip())
    if bad:
        return Verification(False, bad, "figures not found in calculations")
    for figure in required or []:
        if not _is_allowed(figure, numbers_in_text(reply)) and not any(
            abs(round(figure) - n) < 0.001 for n in numbers_in_text(reply)
        ):
            return Verification(False, [str(figure)], "dropped the main figure")
    return Verification(True, [])
