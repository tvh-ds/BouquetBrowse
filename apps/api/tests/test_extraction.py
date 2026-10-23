import pytest

from bouquetbrowse.extraction import extract_caption, extract_prices, validate_grounding


@pytest.mark.parametrize(
    "text,amount,currency",
    [
        ("Giá 650k", 650000, "VND"),
        ("Giá 650.000đ", 650000, "VND"),
        ("650,000 VND", 650000, "VND"),
        ("Giá 1tr2", 1200000, "VND"),
        ("Giá 1tr200", 1200000, "VND"),
        ("Giá 1,2 triệu", 1200000, "VND"),
        ("Giá 1.2tr", 1200000, "VND"),
        ("Price 19.50 USD", 1950, "USD"),
        ("650 nghìn", 650000, "VND"),
        ("Price 650000 VND", 650000, "VND"),
    ],
)
def test_price_formats(text, amount, currency):
    prices, warnings = extract_prices(text)
    assert not warnings
    assert prices[0].amount_min == amount
    assert prices[0].currency == currency


def test_bare_number_is_not_a_price():
    assert extract_prices("Bó hoa mã 650, gồm 20 cành")[0] == []


def test_components_and_spans():
    caption = "20 roses, 650k. Delivery 50k; deposit 100k"
    prices, _ = extract_prices(caption)
    assert [(p.component, p.amount_min) for p in prices] == [
        ("bouquet", 650000),
        ("delivery", 50000),
        ("deposit", 100000),
    ]
    for p in prices:
        assert caption[p.evidence.start : p.evidence.end] == p.evidence.quote


def test_range_and_from():
    prices, _ = extract_prices("Giá 650k–850k")
    assert len(prices) == 1
    assert (prices[0].kind, prices[0].amount_min, prices[0].amount_max) == ("range", 650000, 850000)
    assert extract_prices("Giá từ 400k")[0][0].kind == "from"


def test_old_and_promotional_price():
    prices, _ = extract_prices("Giá gốc 750k; giảm còn 650k")
    assert [p.kind for p in prices] == ["previous", "promotion"]


@pytest.mark.parametrize("caption", ["Giá 1tr20", "Giá 1.20đ"])
def test_ambiguous_amounts_abstain(caption):
    prices, warnings = extract_prices(caption)
    assert not prices
    assert warnings


def test_flowers_are_not_colors():
    result = extract_caption("Bó hoa hồng, 20 cành, 650k")
    assert result.primary_flower.value == "rose"
    assert result.color.value is None
    assert result.stem_count.value == 20


def test_grounded_mixed_language():
    text = "Pink rose bouquet 🌸 20 roses, giấy gói. 650k. Preorder 2 days. Delivery available."
    result = validate_grounding(extract_caption(text), text)
    assert result.color.value == "pink"
    assert result.lead_days.value == 2
    assert result.delivery.value is True
    assert result.stem_count.calibrated_confidence is None


def test_missing_facts_are_unknown():
    result = extract_caption("Một món quà cho ngày thật đẹp ❤️")
    assert result.stem_count.value is None
    assert result.delivery.value is None
    assert result.prices == []


def test_multiple_product_prices_require_review():
    result = extract_caption("Bó A 650k, bó B 850k")
    assert any("Multiple product" in warning for warning in result.warnings)


def test_model_cannot_invent_prices():
    text = "Pink rose bouquet, 650k"
    result = extract_caption(text)
    result.prices[0].amount_min = result.prices[0].amount_max = 900000
    with pytest.raises(ValueError, match="not grounded"):
        validate_grounding(result, text)


def test_model_cannot_infer_commercial_fields():
    text = "Pink rose bouquet"
    result = extract_caption(text)
    result.stem_count.value = 20
    result.stem_count.status = "visual_inference"
    with pytest.raises(ValueError, match="cannot be inferred"):
        validate_grounding(result, text)
