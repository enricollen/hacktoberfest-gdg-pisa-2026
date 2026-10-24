"""Rule-based understanding, used when Gemma is unavailable (or misses the name).

Deliberately simple Italian keyword matching: good enough to keep the tasting moving on a bad
network, never as good as the LLM.
"""

import re

from app.agent.state import Item

_STOP_AFTER_SONO = {
    "allergico",
    "allergica",
    "allergici",
    "intollerante",
    "intolleranti",
    "un",
    "una",
    "uno",
    "il",
    "la",
    "lo",
    "i",
    "le",
    "gli",
    "molto",
    "goloso",
    "golosa",
    "golosi",
    "pronto",
    "pronta",
    "qui",
    "io",
    "di",
    "per",
    "a",
    "in",
    "vegano",
    "vegana",
    "celiaco",
    "celiaca",
    "proprio",
    "davvero",
    "anche",
    "sempre",
    "tanto",
    "più",
    "piu",
    "fan",
    "amante",
    "appassionato",
    "appassionata",
    "contento",
    "contenta",
    "felice",
    "curioso",
    "curiosa",
}
_NOT_A_NAME = _STOP_AFTER_SONO | {
    "si",
    "sì",
    "no",
    "ok",
    "okay",
    "ciao",
    "salve",
    "buongiorno",
    "buonasera",
    "grazie",
    "boh",
    "mah",
    "allora",
    "ehm",
    "eh",
    "fondente",
    "latte",
    "bianco",
    "cioccolato",
    "niente",
}
_NAME_PATTERNS = (
    r"\bmi chiamo\s+([a-zà-ÿ']+)",
    r"\bil mio nome (?:è|e)\s+([a-zà-ÿ']+)",
    r"\bchiamami\s+([a-zà-ÿ']+)",
    r"\b(?:io )?sono\s+(?:il |la )?([a-zà-ÿ']+)",
    r"\bqui (?:è|e|c'è)\s+([a-zà-ÿ']+)",
)

_NEGATIVE_CLAUSE = ("non mi piac", "odio", "detesto", "non amo", "non sopporto", "non mi va")
_ALLERGY_CLAUSE = ("allerg", "intoller", "non posso mangiare", "non posso")
_SYNONYMS = {
    "nocciole": "nocciola",
    "noccioline": "nocciola",
    "mandorle": "mandorla",
    "pistacchi": "pistacchio",
    "lamponi": "lampone",
    "arance": "arancia",
    "agrumi": "agrumi",
    "noci": "noci pecan",
    "frutta secca": "frutta secca",
    "frutti di bosco": "frutti rossi",
    "frutti rossi": "frutti rossi",
    "fragole": "frutti rossi",
    "amaro": "fondente",
    "extra fondente": "fondente",
    "cacao": "cacao amaro",
    "caffe": "caffè",
    "caffè": "caffè",
    "cocco": "cocco",
    "caramello": "caramello",
    "frutta": "frutta",
}

_POSITIVE = (
    "buonissim",
    "ottim",
    "squisit",
    "delizios",
    "fantastic",
    "spettacol",
    "favolos",
    "eccezional",
    "strepitos",
    "divin",
    "perfett",
    "mi è piaciut",
    "mi e piaciut",
    "adoro",
    "top",
    "meraviglios",
    "buono",
    "buona",
    "bello",
    "bella",
    "mi piace",
)
_NEGATIVE = (
    "non mi è piaciut",
    "non mi e piaciut",
    "non mi piace",
    "cattiv",
    "pessim",
    "schifo",
    "non mi ha convinto",
    "troppo",
    "disgust",
    "non buono",
    "non era buono",
)
_MEH = ("così così", "cosi cosi", "insomma", "mah", "normale", "niente di che", "carino")


def _clauses(text: str) -> list[str]:
    return [
        c.strip() for c in re.split(r"[.,;!?]|\bma\b|\bperò\b|\bpero\b", text.lower()) if c.strip()
    ]


def extract_name(text: str) -> str | None:
    lowered = text.lower()
    for pattern in _NAME_PATTERNS:
        for match in re.finditer(pattern, lowered):
            candidate = match.group(1).strip("'")
            if candidate not in _NOT_A_NAME and len(candidate) >= 2:
                return candidate.title()
    # A bare one/two word answer ("Luca.", "Luca Rossi") is the name itself.
    words = re.findall(r"[a-zà-ÿ']+", lowered)
    if 1 <= len(words) <= 2 and words[0] not in _NOT_A_NAME and len(words[0]) >= 2:
        return words[0].title()
    return None


def _vocabulary(items: list[Item]) -> dict[str, str]:
    vocab = dict(_SYNONYMS)
    for item in items:
        vocab[item["chocolate"]] = item["chocolate"]
        for flavor in item["flavors"]:
            vocab[flavor.lower()] = flavor.lower()
    vocab["al latte"] = "latte"
    vocab["bianco"] = "bianco"
    vocab["fondente"] = "fondente"
    return vocab


def extract_tastes(text: str, items: list[Item]) -> tuple[list[str], list[str], list[str]]:
    """(likes, dislikes, allergies) found in a free-form answer."""
    vocab = _vocabulary(items)
    likes: list[str] = []
    dislikes: list[str] = []
    allergies: list[str] = []
    for clause in _clauses(text):
        found = [
            canon for word, canon in vocab.items() if re.search(rf"\b{re.escape(word)}\b", clause)
        ]
        if any(k in clause for k in _ALLERGY_CLAUSE):
            target = allergies
            found = found or [clause.split("allerg")[-1].strip(" aicoe")]
        elif any(k in clause for k in _NEGATIVE_CLAUSE):
            target = dislikes
        else:
            target = likes
        for f in found:
            if f and f not in target:
                target.append(f)
    return likes, dislikes, allergies


def rating_from_text(text: str) -> int | None:
    lowered = text.lower()
    if any(k in lowered for k in _NEGATIVE):
        return 2
    if any(k in lowered for k in _MEH):
        return 3
    strong = ("buonissim", "squisit", "fantastic", "spettacol", "divin", "strepitos", "adoro")
    if any(k in lowered for k in strong):
        return 5
    if any(k in lowered for k in _POSITIVE):
        return 4
    return None


def reaction(rating: int | None) -> str:
    if rating is None:
        return "Grazie del racconto!"
    if rating >= 5:
        return "Evviva, che soddisfazione!"
    if rating == 4:
        return "Bene, mi fa proprio piacere!"
    if rating == 3:
        return "Grazie della sincerità!"
    return "Peccato, rimediamo subito!"
