"""Turn raw statement text into a clean merchant name and a category."""

import re

from ..categories import INCOME, OTHER, TRANSFERS

# Payment processors and bank prefixes that sit in front of the real merchant name.
_PREFIXES = re.compile(
    r"^(?:(?:pos|debit|visa|mastercard|mc|purchase|payment|pre-?authorized|pre-?auth|pap|ach|"
    r"contactless|recurring|card|point of sale|checkcard|apple pay|google pay|interac purchase|"
    r"idp purchase|fpos|opos|sq|tst|sp|py|pp|paypal|zettle|clover|dd|doordash\*)\s*[*#:\-]?\s+"
    r"|(?:sq|tst|sp|py|pp|paypal|zettle|in)\s*\*\s*)+",
    re.IGNORECASE,
)
_NOISE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bref(?:erence)?\s*[#:]?\s*\w+",
        r"\b(?:auth|trace|conf|txn|id)\s*[#:]\s*\w+",
        r"#\s*\d+",
        r"\*+\s*\w*\d\w*",
        r"\b\d{2}[/\-]\d{2}(?:[/\-]\d{2,4})?\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b[a-z]*\d{4,}[a-z0-9]*\b",
        r"\bx{2,}\d*\b",
        r"https?://\S+",
        r"\bwww\.\S+",
        r"\.(?:com|ca|net|org)\b(?:/\S*)?",
    )
]
_TRAILING_PLACE = re.compile(
    r"[\s,]+(?:toronto|mississauga|london|ottawa|montreal|vancouver|calgary|edmonton|winnipeg|"
    r"hamilton|waterloo|kitchener|brampton|markham|dubai|new york|san francisco|seattle|"
    r"amsterdam|luxembourg|on|bc|ab|qc|mb|ns|nb|sk|nl|pe|ca|can|us|usa|uae|ny|wa|nl)"
    r"(?:[\s,]+(?:on|bc|ab|qc|mb|ns|nb|sk|ca|can|us|usa))*\s*$",
    re.IGNORECASE,
)
_TRAILING_WORDS = re.compile(
    r"(?:\s+(?:pap|pad|inc|ltd|llc|corp|co|subscription|payment|pmt|autopay|clubs?))+\s*$",
    re.IGNORECASE,
)
_UNSAFE = re.compile(r"[^\w\s&'.\-+]", re.UNICODE)
_SMALL_WORDS = {"and", "of", "the", "de", "la", "du", "for"}
_KEEP_UPPER = {"ATM", "KFC", "LCBO", "TTC", "TD", "RBC", "BMO", "CIBC", "IKEA", "UPS", "AMC", "H&M"}

# Known merchants: pattern -> (display name, category). Order matters: first match wins.
KNOWN: list[tuple[str, str, str]] = [
    # Money movement first, so transfers never count as spending.
    (r"e-?transfer|etransfer|interac e|e-tfr", "Interac e-Transfer", TRANSFERS),
    (
        r"credit card payment|payment - thank you|payment thank you|card payment|"
        r"pymt.*(visa|mastercard|amex)|(visa|mastercard|amex).*pymt",
        "Credit card payment",
        TRANSFERS,
    ),
    (
        r"\b(transfer|xfer|tfr)\b|\bto savings\b|from savings\b|wealthsimple|questrade",
        "Transfer",
        TRANSFERS,
    ),
    (r"payroll|salary|direct dep|pay\s?cheque|paycheck|\bpay\b.*\bdep", "Payroll", INCOME),
    (
        r"government of canada|canada fed|\bcra\b|ei canada|gst credit|osap",
        "Government payment",
        INCOME,
    ),
    (r"interest (paid|earned|credit)|\binterest\b$", "Interest earned", INCOME),
    # Delivery before restaurants and rides.
    (r"uber\s*\*?\s*eats|ubereats", "Uber Eats", "Food Delivery"),
    (r"skip\s?the\s?dishes|skipthedishes", "SkipTheDishes", "Food Delivery"),
    (r"doordash", "DoorDash", "Food Delivery"),
    (r"instacart", "Instacart", "Groceries"),
    (r"\buber\b", "Uber", "Transport"),
    (r"\blyft\b", "Lyft", "Transport"),
    (
        r"presto|\bttc\b|go transit|translink|\bmetro?link\b|\bstm\b|\boc transpo\b",
        "Transit",
        "Transport",
    ),
    (
        r"petro.?canada|shell\b|esso\b|chevron|ultramar|pioneer gas|\bbp\b|fuel|gas station",
        "Fuel",
        "Transport",
    ),
    (r"impark|green p\b|parking|honk mobile|paybyphone", "Parking", "Transport"),
    # Subscriptions.
    (r"netflix", "Netflix", "Subscriptions"),
    (r"spotify", "Spotify", "Subscriptions"),
    (r"disney\s*\+?|disneyplus", "Disney+", "Subscriptions"),
    (r"crave", "Crave", "Subscriptions"),
    (r"prime video|amazon prime|amzn prime|prime member", "Amazon Prime", "Subscriptions"),
    (r"youtube|google \*?premium", "YouTube Premium", "Subscriptions"),
    (r"apple\.com/bill|apple music|icloud|itunes", "Apple services", "Subscriptions"),
    (r"google\s*\*?\s*(one|storage)", "Google One", "Subscriptions"),
    (r"microsoft\s*\*?\s*(365|office)", "Microsoft 365", "Subscriptions"),
    (r"adobe", "Adobe", "Subscriptions"),
    (r"openai|chatgpt", "ChatGPT", "Subscriptions"),
    (r"anthropic|claude\.ai", "Claude", "Subscriptions"),
    (r"headspace", "Headspace", "Subscriptions"),
    (r"calm\.com|calm app", "Calm", "Subscriptions"),
    (r"audible", "Audible", "Subscriptions"),
    (r"patreon", "Patreon", "Subscriptions"),
    (r"github", "GitHub", "Subscriptions"),
    (r"dropbox", "Dropbox", "Subscriptions"),
    # Groceries.
    (r"loblaws?", "Loblaws", "Groceries"),
    (r"no\s?frills", "No Frills", "Groceries"),
    (r"food\s?basics", "Food Basics", "Groceries"),
    (r"\bfreshco\b", "FreshCo", "Groceries"),
    (r"\bsobeys\b", "Sobeys", "Groceries"),
    (r"\bmetro\b", "Metro", "Groceries"),
    (r"t\s?&\s?t supermarket|t&t", "T&T Supermarket", "Groceries"),
    (r"whole\s?foods", "Whole Foods", "Groceries"),
    (r"costco", "Costco", "Groceries"),
    (r"walmart|wal-mart", "Walmart", "Groceries"),
    (r"trader joe", "Trader Joe's", "Groceries"),
    (r"grocery|supermarket|market\b", "", "Groceries"),
    # Dining.
    (r"tim hortons?|tims\b", "Tim Hortons", "Dining"),
    (r"starbucks|sbux", "Starbucks", "Dining"),
    (r"second cup", "Second Cup", "Dining"),
    (r"mcdonald", "McDonald's", "Dining"),
    (r"a&w\b", "A&W", "Dining"),
    (r"subway", "Subway", "Dining"),
    (r"chipotle", "Chipotle", "Dining"),
    (
        r"pizza|sushi|ramen|shawarma|burger|bistro|grill|restaurant|cafe|café|coffee|kitchen|"
        r"izakaya|banh mi|\bthai\b|\bbar\b|pub\b|taqueria|bakery|tacos?\b|noodle|diner|eatery",
        "",
        "Dining",
    ),
    # Housing and utilities.
    (r"\brent\b|property mgmt|property management|landlord|tridel|capreit", "Rent", "Housing"),
    (r"\bmortgage\b", "Mortgage", "Housing"),
    (r"toronto hydro", "Toronto Hydro", "Utilities"),
    (r"rogers", "Rogers", "Utilities"),
    (r"teksavvy", "TekSavvy", "Utilities"),
    (r"sonnet", "Sonnet Insurance", "Insurance"),
    (r"goodlife", "GoodLife Fitness", "Health"),
    (r"nslsc|student loan", "Student loan", "Debt Payments"),
    (r"shoppers drug", "Shoppers Drug Mart", "Health"),
    (
        r"toronto hydro|london hydro|hydro|enbridge|bc hydro|fortis|water bill|utilities|dewa\b",
        "",
        "Utilities",
    ),
    (
        r"rogers|bell canada|bell mobility|telus|fido|koodo|virgin (plus|mobile)|freedom mobile|"
        r"public mobile|mobilicity|teksavvy|shaw\b|verizon|at&t|t-mobile|comcast|etisalat|\bdu\b",
        "",
        "Utilities",
    ),
    # Insurance, health, education.
    (r"insurance|manulife|sun life|intact|desjardins ins|aviva|geico|state farm", "", "Insurance"),
    (
        r"shoppers drug|pharmacy|rexall|dental|dentist|clinic|physio|optometr|hospital|walgreens|cvs\b",
        "",
        "Health",
    ),
    (r"goodlife|gym|fitness|yoga|ymca|peloton", "", "Health"),
    (
        r"university|college|tuition|western univ|campus store|coursera|udemy|textbook",
        "",
        "Education",
    ),
    # Shopping.
    (r"amazon|amzn|\bamz\b", "Amazon", "Shopping"),
    (r"best\s?buy", "Best Buy", "Shopping"),
    (r"winners|marshalls|homesense", "Winners", "Shopping"),
    (r"\bikea\b", "IKEA", "Shopping"),
    (r"canadian tire", "Canadian Tire", "Shopping"),
    (r"home depot", "Home Depot", "Shopping"),
    (r"zara\b|h&m|uniqlo|gap\b|old navy|lululemon|aritzia|sport chek|nike", "", "Shopping"),
    (r"indigo|chapters", "Indigo", "Shopping"),
    (r"dollarama", "Dollarama", "Shopping"),
    (r"\betsy\b|\bshein\b|\btemu\b|\bebay\b|\baliexpress\b", "", "Shopping"),
    # Entertainment and travel.
    (r"cineplex|\bamc\b|landmark cinemas", "Cineplex", "Entertainment"),
    (r"ticketmaster|stubhub|steam\b|steamgames|playstation|xbox|nintendo", "", "Entertainment"),
    (
        r"air canada|westjet|porter air|flair air|delta air|united air|emirates|expedia|booking\.com|"
        r"airbnb|\bvia rail\b|hotel|marriott|hilton|flighthub",
        "",
        "Travel",
    ),
    # Personal care, gifts, fees, debt.
    (r"salon|barber|spa\b|sephora|nails", "", "Personal Care"),
    (r"donation|charity|red cross|unicef|\bgofundme\b", "", "Gifts & Donations"),
    (
        r"monthly (account )?fee|service (fee|charge)|overdraft|nsf|annual fee|atm fee|interest charge"
        r"|foreign (exchange|transaction)",
        "",
        "Fees",
    ),
    (
        r"loan payment|student loan|nslsc|line of credit|car loan|auto loan|klarna|affirm|afterpay",
        "",
        "Debt Payments",
    ),
    (r"\batm\b|cash withdrawal|abm\b", "ATM withdrawal", TRANSFERS),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), name, cat) for p, name, cat in KNOWN]


def _title(text: str) -> str:
    words = []
    for index, word in enumerate(text.split()):
        upper = word.upper()
        if upper in _KEEP_UPPER:
            words.append(upper)
        elif index and word.lower() in _SMALL_WORDS:
            words.append(word.lower())
        else:
            words.append(word[:1].upper() + word[1:].lower())
    return " ".join(words)


def _strip_noise(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip()
    previous = None
    while previous != text:
        previous = text
        text = _PREFIXES.sub("", text).strip()
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    text = _UNSAFE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -.&'+")
    for _ in range(3):
        stripped = _TRAILING_PLACE.sub("", text).strip(" -.")
        if not stripped or stripped == text:
            break
        text = stripped
    return _TRAILING_WORDS.sub("", text).strip(" -.") or text


def clean_merchant(raw: str) -> str:
    """A short, display-safe name. Long digit runs and names in free text never survive this."""
    for pattern, name, _category in _COMPILED:
        if name and pattern.search(raw):
            return name
    cleaned = _strip_noise(raw)
    if not cleaned:
        return "Unknown merchant"
    return _title(cleaned)[:60]


def categorize(
    raw: str, merchant: str, amount_cents: int, rules: dict[str, str]
) -> tuple[str, str]:
    """Return (category, source). User corrections always win over built-in patterns."""
    if merchant in rules:
        return rules[merchant], "user"
    for pattern, _name, category in _COMPILED:
        if pattern.search(raw) or pattern.search(merchant):
            return category, "rule"
    return (INCOME if amount_cents > 0 else OTHER), "rule"
