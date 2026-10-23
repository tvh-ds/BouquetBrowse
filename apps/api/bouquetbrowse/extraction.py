"""Deterministic candidates, evidence spans and conservative Vietnamese parsing."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .schemas import Evidence, ExtractedField, PriceClaim, ProductExtraction

FLOWERS = {
    "rose": r"\broses?\b|hoa hồng|bông hồng|cành hồng",
    "tulip": r"tulips?",
    "sunflower": r"sunflowers?|hướng dương",
    "lisianthus": r"lisianthus|cát tường",
    "lily": r"\blil(?:y|ies)\b|hoa ly|hoa loa kèn",
    "orchid": r"orchids?|hoa lan|hồ điệp",
    "chrysanthemum": r"chrysanthemum|hoa cúc|cúc họa mi|dais(?:y|ies)",
    "hydrangea": r"hydrangea|cẩm tú cầu",
    "carnation": r"carnation|cẩm chướng",
    "baby-breath": r"baby.?s? breath|hoa baby",
    "lotus": r"lotus|hoa sen",
    "peony": r"peon(?:y|ies)|mẫu đơn",
}
COLORS = {
    "pink": r"\bpink\b|màu hồng|hồng phấn|hồng pastel|hồng nhạt",
    "white": r"\bwhite\b|trắng",
    "yellow": r"\byellow\b|vàng",
    "red": r"\bred\b|màu đỏ|đỏ",
    "purple": r"\bpurple\b|\blavender\b|tím",
    "orange": r"\borange\b|màu cam",
}
ARRANGEMENTS = {
    "bouquet": r"bouquet|bó hoa|\bbó\b",
    "basket": r"basket|giỏ hoa",
    "box": r"flower box|hộp hoa",
    "vase": r"vase|bình hoa",
}
MONEY = re.compile(
    r"(?<![\w.,])(?P<number>\d+(?:[.,]\d{1,3})*)\s*(?P<unit>triệu|trieu|tr|nghìn|nghin|k|vnd|usd|đ|₫|\$)(?P<tail>\d{1,3})?(?!\w)",
    re.I,
)


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d")) if unicodedata.category(c) != "Mn"
    )


def evidence(caption: str, start: int, end: int):
    return Evidence(quote=caption[start:end], start=start, end=end)


def unknown():
    return ExtractedField(value=None, status="unknown", evidence_refs=[])


def find_field(caption: str, vocabulary: dict):
    for value, pattern in vocabulary.items():
        match = re.search(pattern, caption, re.I)
        if match:
            return ExtractedField(value=value, status="stated", evidence_refs=[evidence(caption, *match.span())])
    return unknown()


def parse_amount(number: str, unit: str, tail: str | None):
    unit = fold(unit)
    if unit in {"tr", "trieu"}:
        if tail and len(tail) == 2:
            raise ValueError("Ambiguous million suffix")
        base = Decimal(number.replace(",", ".")) * 1_000_000
        if tail:
            base += int(tail.ljust(3, "0")) * 1000
    elif unit in {"k", "nghin"}:
        if tail:
            raise ValueError("Unexpected price suffix")
        base = Decimal(number.replace(",", ".")) * 1000
    elif unit in {"usd", "$"}:
        base = Decimal(number.replace(",", "")) * 100
    else:
        groups = re.split(r"[.,]", number)
        if len(groups) > 1 and not all(len(part) == 3 for part in groups[1:]):
            raise ValueError("Ambiguous currency separator")
        base = Decimal("".join(groups))
    if base != base.to_integral_value() or base < 0 or base > 10**12:
        raise ValueError("Invalid monetary precision or bounds")
    return int(base)


def extract_prices(caption: str):
    claims, warnings = [], []
    for match in MONEY.finditer(caption):
        try:
            amount = parse_amount(match["number"], match["unit"], match["tail"])
        except (ValueError, InvalidOperation):
            warnings.append(f"Ambiguous amount: {match[0]}")
            continue
        before = fold(caption[max(0, match.start() - 35) : match.start()])
        # A punctuation/line boundary prevents a delivery label leaking to a later bouquet price.
        context = re.split(r"[;!\n]", before)[-1]
        component = (
            "delivery"
            if re.search(r"(?:ship|delivery|giao hang|phi giao)[^\d]{0,15}$", context)
            else "deposit"
            if re.search(r"(?:coc|deposit)[^\d]{0,12}$", context)
            else "bouquet"
        )
        kind = (
            "from"
            if re.search(r"(?:tu|from)\s*$", context)
            else "previous"
            if re.search(r"(?:gia goc|gia cu|was)\s*$", context)
            else "promotion"
            if re.search(r"(?:giam con|sale|now)\s*$", context)
            else "exact"
        )
        unit = fold(match["unit"])
        currency = "USD" if unit in {"usd", "$"} else "VND"
        basis = "explicit" if unit in {"usd", "$", "vnd", "đ", "₫"} or match["unit"] == "đ" else "seller_market"
        claim = PriceClaim(
            amount_min=amount,
            amount_max=amount,
            currency=currency,
            currency_basis=basis,
            kind=kind,
            component=component,
            evidence=evidence(caption, *match.span()),
        )
        if claims:
            previous = claims[-1]
            gap = fold(caption[previous.evidence.end : match.start()])
            if previous.component == component and re.fullmatch(r"\s*(?:-|–|—|den|to)\s*", gap):
                previous.kind = "range"
                previous.amount_max = max(previous.amount_min, amount)
                previous.amount_min = min(previous.amount_min, amount)
                previous.evidence = evidence(caption, previous.evidence.start, match.end())
                continue
        claims.append(claim)
    current = [c for c in claims if c.component == "bouquet" and c.kind != "previous"]
    if len(current) > 1:
        warnings.append("Multiple product prices: associate configurations before publication")
    return claims, warnings


def extract_caption(caption: str) -> ProductExtraction:
    prices, warnings = extract_prices(caption)
    composition = [(name, re.search(pattern, caption, re.I)) for name, pattern in FLOWERS.items()]
    composition = [(name, match) for name, match in composition if match]
    primary = find_field(caption, FLOWERS)
    if len(composition) > 1:
        primary = ExtractedField(
            value="mixed", status="stated", evidence_refs=[evidence(caption, *match.span()) for _, match in composition]
        )
    count_match = re.search(r"\b(\d{1,4})\s*(?:roses?\b|stems?\b|bông\b|cành\b|hoa hồng\b)", caption, re.I)
    stem_count = (
        ExtractedField(
            value=int(count_match[1]), status="stated", evidence_refs=[evidence(caption, *count_match.span())]
        )
        if count_match
        else unknown()
    )
    lead = re.search(
        r"(?:preorder|pre.order|prepare|đặt trước|đặt hoa trước|chuẩn bị)[^\d\n]{0,15}(\d{1,2})\s*(?:days?|ngày)",
        caption,
        re.I,
    )
    lead_days = (
        ExtractedField(value=int(lead[1]), status="stated", evidence_refs=[evidence(caption, *lead.span())])
        if lead
        else unknown()
    )
    delivery_match = re.search(r"delivery available|có giao hàng|giao hàng nội thành|hỗ trợ giao hàng", caption, re.I)
    delivery = (
        ExtractedField(value=True, status="stated", evidence_refs=[evidence(caption, *delivery_match.span())])
        if delivery_match
        else unknown()
    )
    wrapping = find_field(caption, {"paper": r"paper wrapping|giấy gói|giấy kraft", "fabric": r"vải|fabric"})
    return ProductExtraction(
        arrangement=find_field(caption, ARRANGEMENTS),
        primary_flower=primary,
        flower_composition=ExtractedField(
            value=[name for name, _ in composition] or None,
            status="stated" if composition else "unknown",
            evidence_refs=[evidence(caption, *match.span()) for _, match in composition],
        ),
        color=find_field(caption, COLORS),
        stem_count=stem_count,
        lead_days=lead_days,
        delivery=delivery,
        wrapping=wrapping,
        style=find_field(
            caption, {"romantic": r"romantic|lãng mạn", "natural": r"natural|tự nhiên", "minimal": r"minimal|tối giản"}
        ),
        occasion=find_field(
            caption,
            {
                "birthday": r"birthday|sinh nhật",
                "anniversary": r"anniversary|kỷ niệm",
                "graduation": r"graduation|tốt nghiệp",
            },
        ),
        prices=prices,
        warnings=warnings,
    )


def validate_grounding(result: ProductExtraction, caption: str):
    deterministic_result = extract_caption(caption)
    for name in type(result).model_fields:
        field = getattr(result, name)
        if isinstance(field, ExtractedField):
            for ref in field.evidence_refs:
                if caption[ref.start : ref.end] != ref.quote or ref.end <= ref.start:
                    raise ValueError(f"Invalid source evidence for {name}")
            if field.value is not None and field.status in {"stated", "context_inference"} and not field.evidence_refs:
                raise ValueError(f"Missing evidence for {name}")
            if name in {"stem_count", "lead_days", "delivery"} and field.value is not None and field.status != "stated":
                raise ValueError(f"Commercial field cannot be inferred: {name}")
            if (
                name in {"stem_count", "lead_days", "delivery"}
                and field.value is not None
                and getattr(deterministic_result, name).value != field.value
            ):
                raise ValueError(f"Commercial value does not match source parsing: {name}")
            if field.calibrated_confidence is not None:
                raise ValueError("Model output cannot self-certify calibrated confidence")
    deterministic, _ = extract_prices(caption)
    candidates = {
        (p.amount_min, p.amount_max, p.currency, p.component, p.kind, p.evidence.quote) for p in deterministic
    }
    for p in result.prices:
        if caption[p.evidence.start : p.evidence.end] != p.evidence.quote:
            raise ValueError("Invalid price evidence")
        if (p.amount_min, p.amount_max, p.currency, p.component, p.kind, p.evidence.quote) not in candidates:
            raise ValueError("Model price is not grounded in deterministic monetary evidence")
    return result
