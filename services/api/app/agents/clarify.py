"""Una pregunta antes de buscar, cuando el nombre todavía cambia el precio.

El orden es fijo: el modelo, después nuevo o usado, después la capacidad.
"Me da igual" cierra solo esa pregunta. Una respuesta de texto vale igual que tocar la fila.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.lib.catalogo import PRODUCTOS

ANY = "Me da igual"
_MAX_TRACKED = 500
_CONDITION_CATEGORIES = frozenset({"telefonos", "tablets", "laptops", "consolas"})
_STORAGE_CATEGORIES = frozenset({"telefonos", "tablets", "laptops"})
_ROW_TITLE = 24

# El catálogo no trae todas las variantes (falta el iPhone 14 Pro, por ejemplo).
# Estas sí cambian el precio y son las que hay que ofrecer.
_IPHONE_TIERS = {
    "11": ("", "Pro", "Pro Max"),
    "12": ("", "mini", "Pro", "Pro Max"),
    "13": ("", "mini", "Pro", "Pro Max"),
    "14": ("", "Plus", "Pro", "Pro Max"),
    "15": ("", "Plus", "Pro", "Pro Max"),
    "16": ("", "Plus", "Pro", "Pro Max", "e"),
    "17": ("", "Pro", "Pro Max", "e"),
}
_IPHONE_GENERATIONS = ("11", "12", "13", "14", "15", "16", "17")
_IPHONE = re.compile(
    r"(?<!\w)(iPhone\s+16e|iPhone\s+17e|iPhone\s+1[1-7](?!\d)"
    r"(?:\s+plus|\s+mini|\s+pro\s+max|\s+pro)?|iPhone)(?!\w)",
    re.IGNORECASE,
)
_NOT_THE_DEVICE = re.compile(
    r"\b(fundas?|cargadores?|micas?|protectores?|cables?|vidrios?|forros?|cases?|covers?|"
    r"repuestos?|pantallas?|baterias?)\b"
)
_RESOLVED_SUFFIX = re.compile(r"(?:pro max|pro|plus|mini|slim|ultra)$")
_WAIVE = re.compile(r"\b(me da igual|da igual|cualquiera|no importa|lo que sea|me es igual)\b")
_USED = re.compile(r"\b(usad[oa]s?|segunda mano)\b")
_NEW = re.compile(r"\b(nuev[oa]s?|sellad[oa]s?)\b")
_REFURB = re.compile(r"\b(reacondicionad[oa]s?|refurbished)\b")
_CAPACITY = re.compile(r"\b(\d+)\s?(gb|tb)\b")
_BASE_WORD = re.compile(r"\b(normal|regular|basico|sencillo|comun)\b")
_MODEL_SUFFIXES = ("pro max", "plus", "mini", "pro")

_allowed: dict[str, str] = {}


@dataclass(frozen=True)
class Question:
    text: str
    choices: tuple[str, ...]
    dimension: str
    section: str


@dataclass(frozen=True)
class PendingProduct:
    product: str
    closed: frozenset[str]
    family: str


@dataclass(frozen=True)
class Step:
    product: str
    closed: frozenset[str]
    family: str
    question: Question | None


@dataclass(frozen=True)
class _Item:
    name: str
    folded: str
    category: str
    serie: str


@dataclass(frozen=True)
class _Facts:
    family: str
    category: str
    model_options: tuple[str, ...]
    span: tuple[int, int] | None


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(plain.lower().replace("-", " ").split())


def _items() -> tuple[list[_Item], dict[str, list[_Item]]]:
    items: list[_Item] = []
    series: dict[str, list[_Item]] = {}
    for product in PRODUCTOS:
        item = _Item(product["nombre"], _fold(product["nombre"]), product["categoria"], product["serie"])
        items.append(item)
        series.setdefault(product["serie"], []).append(item)
    return items, series


_ITEMS, _SERIES = _items()


def _condition_label(text: str) -> str | None:
    folded = _fold(text)
    if _REFURB.search(folded):
        return "reacondicionado"
    used = _USED.search(folded)
    new = _NEW.search(folded)
    if used and new:
        return None
    if used:
        return "usado"
    if new:
        return "nuevo"
    return None


def _capacity_label(text: str) -> str | None:
    folded = _fold(text)
    match = _CAPACITY.search(folded)
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    # "256" a secas, cuando la persona no escribe GB. 14 o 5 no son capacidades.
    bare = re.search(r"\b(128|256|512)\b", folded)
    if bare:
        return f"{bare.group(1)} GB"
    return None


def _listable(options: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for option in options:
        title = " ".join(option.split())
        if title and len(title) <= _ROW_TITLE and title not in seen:
            seen.append(title)
    if len(seen) < 2:
        return ()
    return tuple(seen)


def _iphone_label(generation: str, tier: str) -> str:
    if tier == "e":
        return f"iPhone {generation}e"
    if tier == "":
        return f"iPhone {generation}"
    return f"iPhone {generation} {tier}"


def _iphone_facts(text: str) -> _Facts | None:
    match = _IPHONE.search(text)
    if not match:
        return None
    parts = _fold(match.group(1)).split()
    if len(parts) == 1:
        options = tuple(f"iPhone {generation}" for generation in _IPHONE_GENERATIONS)
        return _Facts("iphone", "telefonos", options, match.span())
    token = parts[1]
    if token in ("16e", "17e"):
        return _Facts(f"iphone {token}", "telefonos", (), match.span())
    tier = " ".join(parts[2:]) if len(parts) > 2 else None
    if tier is None:
        options = tuple(_iphone_label(token, name) for name in _IPHONE_TIERS[token])
        return _Facts(f"iphone {token}", "telefonos", options, match.span())
    return _Facts(f"iphone {token}", "telefonos", (), match.span())


def _phrase(text: str, phrase: str) -> re.Match[str] | None:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE)


def _catalog_facts(text: str) -> _Facts | None:
    found: list[tuple[_Item, tuple[int, int]]] = []
    for item in _ITEMS:
        match = _phrase(text, item.name)
        if match:
            found.append((item, match.span()))
    if found:
        item, span = max(found, key=lambda pair: len(pair[0].name))
        variants = [other for other in _ITEMS if other.folded.startswith(item.folded + " ")]
        ancestors = [other for other in _ITEMS if item.folded.startswith(other.folded + " ")]
        parent = max(ancestors, key=lambda other: len(other.folded)) if ancestors else item
        if variants and not _RESOLVED_SUFFIX.search(item.folded):
            names = (item.name, *(other.name for other in sorted(variants, key=lambda other: other.name)))
            return _Facts(item.folded, item.category, names, span)
        return _Facts(parent.folded, item.category, (), span)

    folded = _fold(text)
    for serie, members in _SERIES.items():
        if len(serie.split()) < 2 or not 2 <= len(members) <= 9:
            continue
        if serie.lower() not in folded and _fold(serie) not in folded:
            continue
        match = _phrase(text, serie)
        if not match:
            continue
        if any(_phrase(text, member.name) for member in members):
            continue
        names = tuple(member.name for member in sorted(members, key=lambda member: member.name))
        return _Facts(_fold(serie), members[0].category, names, match.span())
    return None


def _facts(text: str) -> _Facts | None:
    if not text.strip() or _NOT_THE_DEVICE.search(_fold(text)):
        return None
    return _iphone_facts(text) or _catalog_facts(text)


def family_of(text: str) -> str | None:
    facts = _facts(text)
    return facts.family if facts else None


def _storage_options(product: str, category: str) -> tuple[str, ...]:
    if category == "laptops":
        return ("256 GB", "512 GB", "1 TB")
    if category not in _STORAGE_CATEGORIES:
        return ()
    folded = _fold(product)
    if re.search(r"\biphone\b", folded) and re.search(r"\bpro\b", folded):
        return ("128 GB", "256 GB", "512 GB", "1 TB")
    return ("128 GB", "256 GB", "512 GB")


def _shared_prefix(options: tuple[str, ...]) -> str:
    rows = [option.split() for option in options]
    prefix: list[str] = []
    for column in zip(*rows, strict=False):
        if len({token.lower() for token in column}) != 1:
            break
        prefix.append(column[0])
    return " ".join(prefix)


def _model_question(options: tuple[str, ...]) -> Question:
    label = _shared_prefix(options)
    text = f"¿Cuál {label} buscas?" if label else "¿Cuál de estos buscas?"
    return Question(text, options + (ANY,), "model", "Modelos")


def next_question(product: str, closed: frozenset[str]) -> Question | None:
    """La próxima elección que cambia el precio, o None si ya se puede buscar."""
    facts = _facts(product)
    if facts is None:
        return None
    if "model" not in closed:
        options = _listable(facts.model_options)
        if len(options) >= 2:
            return _model_question(options)
    if (
        "condition" not in closed
        and facts.category in _CONDITION_CATEGORIES
        and _condition_label(product) is None
    ):
        return Question("¿Lo quieres nuevo o usado?", ("Nuevo", "Usado", ANY), "condition", "Estado")
    if (
        "storage" not in closed
        and facts.category in _STORAGE_CATEGORIES
        and _capacity_label(product) is None
    ):
        sizes = _storage_options(product, facts.category)
        if sizes:
            return Question("¿De cuánta capacidad?", sizes + (ANY,), "storage", "Capacidad")
    return None


def spoken_question(question: Question) -> str:
    options = [choice for choice in question.choices if choice != ANY]
    if not options:
        return question.text
    listed = ", ".join(options)
    if ANY in question.choices:
        return f"{question.text} {listed}, o me da igual."
    return f"{question.text} {listed}."


def _model_synonym(choices: list[str], folded: str) -> str | None:
    for suffix in _MODEL_SUFFIXES:
        if not re.search(rf"\b{suffix}\b", folded):
            continue
        hits = []
        for choice in choices:
            name = _fold(choice)
            if suffix == "pro" and name.endswith("pro max"):
                continue
            if name.endswith(suffix):
                hits.append(choice)
        if hits:
            return max(hits, key=lambda choice: len(_fold(choice)))
    if _BASE_WORD.search(folded):
        bases = [
            choice
            for choice in choices
            if any(_fold(other).startswith(_fold(choice) + " ") for other in choices)
        ]
        if bases:
            return min(bases, key=lambda choice: len(_fold(choice)))
    tail_hits = []
    for choice in choices:
        tail = _fold(choice).split()[-1]
        if len(tail) >= 2 and re.search(rf"\b{re.escape(tail)}\b", folded):
            tail_hits.append(choice)
    if len(tail_hits) == 1:
        return tail_hits[0]
    return None


def match_choice(question: Question, reply: str) -> str | None:
    folded = _fold(reply)
    specific = [choice for choice in question.choices if choice != ANY]
    contained = [choice for choice in specific if _fold(choice) in folded]
    if contained:
        return max(contained, key=lambda choice: len(_fold(choice)))
    if question.dimension == "model":
        synonym = _model_synonym(specific, folded)
        if synonym:
            return synonym
    if question.dimension == "condition":
        label = _condition_label(reply)
        if label == "usado":
            return "Usado"
        if label == "nuevo":
            return "Nuevo"
        if label == "reacondicionado":
            return "reacondicionado"
    if question.dimension == "storage":
        label = _capacity_label(reply)
        if label:
            for choice in specific:
                if _fold(choice) == _fold(label):
                    return choice
        for choice in specific:
            number = choice.split()[0]
            if re.search(rf"\b{re.escape(number)}\b", folded):
                return choice
    if _WAIVE.search(folded):
        return ANY
    return None


def _replace_span(product: str, choice: str) -> str:
    if _fold(choice) in _fold(product):
        return product
    facts = _facts(product)
    if facts and facts.span:
        start, end = facts.span
        return f"{product[:start]}{choice}{product[end:]}".strip()
    return f"{product} {choice}".strip()


def _apply_model(product: str, choice: str, reply: str) -> str:
    if choice == ANY:
        return product
    if _fold(choice) in _fold(reply) and _fold(reply) != _fold(choice):
        return reply.strip()
    return _replace_span(product, choice)


def _mark_closed(product: str, question: Question, choice: str, closed: set[str]) -> None:
    if question.dimension != "model" or choice == ANY:
        closed.add(question.dimension)
        return
    finer = [
        other
        for other in question.choices
        if other not in (choice, ANY) and _fold(other).startswith(_fold(choice) + " ")
    ]
    facts = _facts(product)
    still_open = bool(facts and _listable(facts.model_options))
    if finer or not still_open:
        closed.add("model")


def _absorb(product: str, reply: str, answered: str | None) -> tuple[str, set[str]]:
    closed: set[str] = set()
    if answered != "condition":
        label = _condition_label(reply)
        if label and _condition_label(product) is None:
            product = f"{product} {label}"
            closed.add("condition")
    if answered != "storage":
        label = _capacity_label(reply)
        if label and _capacity_label(product) is None:
            product = f"{product} {label}"
            closed.add("storage")
    return product, closed


def _fresh(text: str) -> Step:
    facts = _facts(text)
    family = facts.family if facts else ""
    return Step(text, frozenset(), family, next_question(text, frozenset()))


def _continue(pending: PendingProduct, text: str) -> Step | None:
    question = next_question(pending.product, pending.closed)
    if question is None:
        return None
    incoming = family_of(text)
    if incoming and incoming != pending.family:
        return None
    choice = match_choice(question, text)
    extra_condition = question.dimension != "condition" and _condition_label(text) is not None
    extra_storage = question.dimension != "storage" and _capacity_label(text) is not None
    if choice is None and not extra_condition and not extra_storage:
        return None
    product = pending.product
    closed = set(pending.closed)
    if choice is not None:
        if question.dimension == "model":
            product = _apply_model(product, choice, text)
        elif question.dimension == "condition":
            if choice != ANY and _condition_label(product) is None:
                word = {"Nuevo": "nuevo", "Usado": "usado"}.get(choice, choice)
                product = f"{product} {word}"
        elif question.dimension == "storage" and choice != ANY and _capacity_label(product) is None:
            product = f"{product} {choice}"
        _mark_closed(product, question, choice, closed)
    product, absorbed = _absorb(product, text, question.dimension if choice else None)
    closed.update(absorbed)
    facts = _facts(product)
    family = facts.family if facts else pending.family
    frozen = frozenset(closed)
    return Step(product, frozen, family, next_question(product, frozen))


def step(pending: PendingProduct | None, message: str) -> Step:
    """Aplica el mensaje a la pregunta abierta, o empieza un producto nuevo."""
    text = " ".join(message.split())
    if pending is not None:
        continued = _continue(pending, text)
        if continued is not None:
            return continued
    return _fresh(text)


def allow_search(user_id: str, product: str) -> None:
    if len(_allowed) > _MAX_TRACKED:
        _allowed.clear()
    _allowed[user_id] = _fold(product)


def search_is_allowed(user_id: str, product: str) -> bool:
    saved = _allowed.get(user_id)
    return saved is not None and saved == _fold(product)


def forget_search(user_id: str) -> None:
    _allowed.pop(user_id, None)


def clear_allowed_searches() -> None:
    _allowed.clear()
