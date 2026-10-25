"""Puntaje de confianza, sin red: null no es 0, y sin cobertura no hay puntaje."""

import unittest
from datetime import UTC, datetime

from pydantic import ValidationError

from app.lib.catalogo import _confianza_texto
from app.lib.contracts import (
    CATALOGS,
    MIN_COVERAGE,
    Adjustment,
    CanonicalProduct,
    Merchant,
    MerchantLink,
    Money,
    Offer,
    RateRef,
    TrustScore,
    TrustSignal,
    verdict_for,
)
from app.lib.trust import (
    PRICE_RED_FLAG,
    AdjustmentBinding,
    Fill,
    Measured,
    aggregate,
    amazon_sold_and_shipped,
    anomaly_from_deviation,
    build_signals,
    close_listings,
    compute_trust,
    entity_id_for,
    facebook_rating_bonus,
    finalize,
    resolve_identities,
    round_half_up,
    score_mercadolibre,
    to_card,
    to_stars,
)

NOW = datetime(2026, 10, 24, tzinfo=UTC)
WORDS = " ".join(["nuevo"] * 40)


def _uniform(formula: str, value: float, pending: set[str] | None = None) -> list[TrustSignal]:
    pending = pending or set()
    values: dict[str, Measured] = {}
    for spec in CATALOGS[formula]:
        if spec.key in pending:
            values[spec.key] = Measured("pending")
        elif spec.filled_by == "nobody":
            values[spec.key] = Measured(None)
        else:
            values[spec.key] = Measured(value)
    return build_signals(formula, values)


def _pair(value, *, stage="final", flags=None, adjustments=None, extra_bonus=0):
    signals = [
        TrustSignal(family="reputacion", key="known", weight=50, value=1),
        TrustSignal(family="reputacion", key="other", weight=50, value=value),
    ]
    return compute_trust(
        "custom-v1",
        signals,
        stage=stage,
        red_flags=flags,
        adjustments=adjustments,
        extra_bonus=extra_bonus,
        now=NOW,
    )


def _merchant(merchant_id, channel, url, links=None, **extra):
    return Merchant(id=merchant_id, name=merchant_id, channel=channel, url=url, links=links or [], **extra)


def _offer(offer_id, merchant_id, trust, *, price=100.0, condition="nuevo", product="phone"):
    priced = price is not None
    return Offer(
        id=offer_id,
        merchant_id=merchant_id,
        product=CanonicalProduct(key=product),
        condition=condition,
        title="Teléfono",
        url=f"https://example.com/{offer_id}",
        seen_at=NOW,
        evidence_ids=["price"],
        trust=trust,
        price=Money(amount=price, currency="USD") if priced else None,
        price_kind="publicado" if priced else "al_dm",
        price_usd=price,
    )


def _ml_item():
    return {
        "id": "MLV123456789",
        "title": "iPhone 15 128 GB",
        "price": 500,
        "currency_id": "USD",
        "condition": "new",
        "pictures": [{}, {}, {}, {}],
        "warranty": "12 meses",
        "seller_id": 99,
        "seller_address": {"state": {"name": "Miranda"}},
    }


def _ml_seller(**reputation):
    base = {
        "level_id": "5_green",
        "power_seller_status": "platinum",
        "transactions": {
            "completed": 340,
            "total": 360,
            "ratings": {"positive": 0.97, "neutral": 0.01, "negative": 0.02},
        },
    }
    base.update(reputation)
    return {
        "id": 99,
        "nickname": "TIENDA",
        "registration_date": "2020-01-15T00:00:00.000-04:00",
        "address": {"state": "Miranda"},
        "seller_reputation": base,
        "status": {"site_status": "active"},
    }


class TrustEngineTest(unittest.TestCase):
    def test_catalogs_sum_to_100_and_keys_are_unique(self):
        aggregator = {"price_anomaly", "photos_original", "linked_socials"}
        for formula, specs in CATALOGS.items():
            keys = [spec.key for spec in specs]
            self.assertEqual(len(keys), len(set(keys)), formula)
            self.assertEqual(sum(spec.weight for spec in specs), 100, formula)
            for spec in specs:
                if spec.key in aggregator:
                    self.assertEqual(spec.filled_by, "aggregator", spec.key)
                if spec.key == "reports":
                    self.assertEqual(spec.filled_by, "nobody")
        self.assertEqual(CATALOGS["ig-v1"][9].weight, 15)  # price_anomaly
        self.assertEqual(next(spec.weight for spec in CATALOGS["fb-v1"] if spec.key == "photos_original"), 20)

    def test_null_is_not_zero(self):
        missing = _pair(None)
        zero = _pair(0)
        self.assertEqual(missing.score, 100)
        self.assertEqual(missing.coverage, 0.5)
        self.assertEqual(zero.score, 50)
        self.assertEqual(zero.coverage, 1)
        self.assertLess(zero.score, missing.score)

    def test_pending_is_not_measured_and_final_cannot_keep_it(self):
        opened = _pair("pending", stage="parcial")
        self.assertIsNone(opened.score)
        self.assertEqual(opened.verdict, "sin_datos")
        self.assertEqual(opened.coverage, 0.5)
        self.assertEqual(opened.stage, "parcial")
        closed = finalize(opened, {}, now=NOW)
        self.assertIsNone(closed.signals[1].value)
        self.assertEqual(closed.score, 100)
        filled = finalize(opened, {"other": Fill(0)}, now=NOW)
        self.assertEqual(filled.score, 50)
        with self.assertRaises(ValidationError):
            TrustScore(
                score=None,
                coverage=0,
                verdict="sin_datos",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                signals=[TrustSignal(family="precio", key="price_anomaly", weight=100, value="pending")],
            )

    def test_coverage_gate_is_only_at_the_close(self):
        wide = _uniform("ml-v1", 1, pending={"price_anomaly"})
        opened = compute_trust("ml-v1", wide, stage="parcial", now=NOW)
        self.assertGreaterEqual(opened.coverage, MIN_COVERAGE)
        self.assertIsNone(opened.score)
        self.assertEqual(opened.verdict, "sin_datos")
        exact = _measured(("account_age", 10), ("thermometer", 15), ("location", 5), ("completeness", 5), ("risk_language", 5))
        closed = compute_trust("ml-v1", exact, stage="final", now=NOW)
        self.assertEqual(closed.coverage, 0.4)
        self.assertEqual(closed.score, 100)
        self.assertEqual(closed.verdict, "confiable")
        short = _measured(("account_age", 10), ("thermometer", 15), ("completeness", 5), ("risk_language", 5))
        blocked = compute_trust("ml-v1", short, stage="final", now=NOW)
        self.assertLess(blocked.coverage, MIN_COVERAGE)
        self.assertIsNone(blocked.score)
        self.assertEqual(blocked.verdict, "sin_datos")
        self.assertIsNone(to_stars(blocked.score))

    def test_red_flag_zeros_even_with_little_coverage(self):
        signals = [
            TrustSignal(family="identidad", key="age", weight=30, value=1),
            TrustSignal(family="reportes", key="reports", weight=70, value=None),
        ]
        score = compute_trust("custom-v1", signals, stage="final", red_flags=["cuenta nueva"], now=NOW)
        self.assertEqual(score.score, 0)
        self.assertEqual(score.verdict, "riesgosa")
        self.assertEqual(score.coverage, 0.3)
        self.assertEqual(to_stars(score.score), 0)
        self.assertEqual(score.reasons[0], "cuenta nueva")

    def test_adjustments_and_marketplace_bonus(self):
        base = _pair(1)
        self.assertEqual(base.score, 100)
        self.assertEqual(_pair(0.6).score, 80)
        penalized = _pair(0.6, adjustments=[Adjustment(source="meta-ads", penalty=15, reasons=["Anuncios muy cortos"])])
        self.assertEqual(penalized.score, 65)
        self.assertEqual(penalized.verdict, "precaucion")
        self.assertIn("Anuncios muy cortos", penalized.reasons)
        self.assertEqual(_pair(0.98).score, 99)
        capped = _pair(0.98, adjustments=[Adjustment(source="meta-ads", bonus=5)])
        self.assertEqual(capped.score, 100)
        flagged = _pair(1, adjustments=[Adjustment(source="meta-ads", red_flags=["Página renombrada"])])
        self.assertEqual(flagged.score, 0)
        self.assertEqual(flagged.verdict, "riesgosa")
        plain = _pair(0.4)
        boosted = _pair(0.4, extra_bonus=facebook_rating_bonus(5, 40, ["Súper vendedor"]))
        self.assertEqual(plain.score, 70)
        self.assertEqual(plain.verdict, "precaucion")
        self.assertEqual(to_stars(plain.score), 3)
        self.assertEqual(facebook_rating_bonus(None, None, None), 0)
        self.assertEqual(boosted.score, 80)
        self.assertEqual(boosted.verdict, "confiable")
        self.assertEqual(to_stars(boosted.score), 4)

    def test_amazon_shortcut_skips_signals(self):
        shortcut = amazon_sold_and_shipped(NOW)
        self.assertEqual(shortcut.score, 95)
        self.assertEqual(shortcut.coverage, 1)
        self.assertEqual(shortcut.verdict, "confiable")
        self.assertEqual(shortcut.signals, [])
        self.assertEqual(to_stars(95), 5)
        scored = compute_trust("amazon-v1", _uniform("amazon-v1", 0.5), stage="final", now=NOW)
        self.assertEqual(scored.score, 50)
        self.assertNotEqual(scored.score, 95)

    def test_stars_match_the_verdict_bands(self):
        self.assertEqual(round_half_up(2.5), 3)
        self.assertEqual(round_half_up(0.5), 1)
        for score in range(101):
            stars = to_stars(score)
            self.assertIsNotNone(stars)
            if stars >= 4:
                self.assertEqual(verdict_for(score), "confiable")
            elif stars >= 2:
                self.assertEqual(verdict_for(score), "precaucion")
            else:
                self.assertEqual(verdict_for(score), "riesgosa")
        self.assertIsNone(to_stars(None))
        self.assertEqual([to_stars(score) for score in (0, 1, 49, 50, 59, 60, 74, 75, 89, 90, 100)], [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])

    def test_reasons_are_ordered_by_how_hard_they_pull(self):
        signals = [
            TrustSignal(family="riesgo", key="light", weight=10, value=0.9, reason="leve"),
            TrustSignal(family="precio", key="heavy", weight=90, value=0, reason="grave"),
        ]
        score = compute_trust("custom-v1", signals, stage="final", red_flags=["bandera"], now=NOW)
        self.assertEqual(score.reasons[:3], ["bandera", "grave", "leve"])

    def test_section_nine_rejects_a_broken_score(self):
        with self.assertRaises(ValidationError):
            TrustScore(
                score=10,
                coverage=1,
                verdict="confiable",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                signals=[TrustSignal(family="precio", key="only", weight=90, value=1)],
            )
        with self.assertRaises(ValidationError):
            TrustScore(
                score=50,
                coverage=1,
                verdict="precaucion",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                signals=[
                    TrustSignal(family="precio", key="same", weight=50, value=1),
                    TrustSignal(family="riesgo", key="same", weight=50, value=0),
                ],
            )
        with self.assertRaises(ValidationError):
            TrustSignal.model_validate({"family": "precio", "key": "x", "weight": 1, "value": 1.5})
        with self.assertRaises(ValidationError):
            TrustSignal.model_validate({"family": "precio", "key": "x", "weight": 1, "value": True})
        with self.assertRaises(ValidationError):
            TrustScore(
                score=None,
                coverage=1,
                verdict="sin_datos",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                signals=[TrustSignal(family="precio", key="only", weight=100, value=1)],
            )
        with self.assertRaises(ValidationError):
            TrustScore(
                score=80,
                coverage=0.2,
                verdict="confiable",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                signals=[
                    TrustSignal(family="precio", key="seen", weight=20, value=1),
                    TrustSignal(family="reportes", key="missing", weight=80, value=None),
                ],
            )
        with self.assertRaises(ValidationError):
            TrustScore(
                score=10,
                coverage=1,
                verdict="precaucion",
                stage="final",
                formula="custom-v1",
                computed_at=NOW,
                red_flags=["estafa"],
                signals=[TrustSignal(family="precio", key="only", weight=100, value=0)],
            )
        with self.assertRaises(ValidationError):
            Offer(
                id="x",
                merchant_id="m",
                product=CanonicalProduct(key="p"),
                condition="nuevo",
                title="x",
                url="https://example.com/x",
                seen_at=NOW,
                evidence_ids=["price"],
                trust=_pair(1),
                price=None,
            )
        dumped = _pair(1).model_dump(mode="json", by_alias=True)
        self.assertIn("computedAt", dumped)
        self.assertEqual(TrustScore.model_validate(dumped).score, 100)
        with self.assertRaises(ValidationError):
            TrustSignal.model_validate({"family": "precio", "key": "x", "weight": 1, "value": 1, "extra": 1})

    def test_price_anomaly_words_and_half_threshold(self):
        value, reason, good = anomaly_from_deviation(-0.43)
        self.assertLess(value, 1)
        self.assertFalse(good)
        self.assertIn("43%", reason)
        value, reason, good = anomaly_from_deviation(-0.10)
        self.assertEqual(value, 1)
        self.assertTrue(good)
        self.assertEqual(reason, "Precio en línea con el mercado")

    def test_catalog_text_uses_75_and_50(self):
        self.assertEqual(_confianza_texto(75), "Vendedor confiable")
        self.assertEqual(_confianza_texto(74), "Buenas referencias")
        self.assertEqual(_confianza_texto(50), "Buenas referencias")
        self.assertEqual(_confianza_texto(49), "Pocas referencias")


class MercadoLibreScoreTest(unittest.TestCase):
    def test_a_strong_seller_scores_100_with_reports_unmeasured(self):
        score = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertEqual(score.stage, "final")
        self.assertEqual(score.formula, "ml-v1")
        self.assertEqual(score.coverage, 0.9)
        self.assertEqual(score.score, 100)
        self.assertEqual(score.verdict, "confiable")
        self.assertEqual(to_stars(score.score), 5)
        self.assertTrue(all(signal.value != "pending" for signal in score.signals))
        reports = next(signal for signal in score.signals if signal.key == "reports")
        self.assertIsNone(reports.value)

    def test_no_seller_data_is_sin_datos_not_a_low_score(self):
        score = score_mercadolibre({"title": "x", "pictures": []}, None, description="", now=NOW, stage="final")
        self.assertLess(score.coverage, MIN_COVERAGE)
        self.assertIsNone(score.score)
        self.assertEqual(score.verdict, "sin_datos")

    def test_zero_reputation_is_measured_and_a_red_level_with_sales_is_a_flag(self):
        values = {spec.key: Measured(1.0) for spec in CATALOGS["ml-v1"] if spec.key not in {"power_seller", "reports"}}
        values["reports"] = Measured(None)
        values["power_seller"] = Measured(0)
        zero = compute_trust("ml-v1", build_signals("ml-v1", values), stage="final", now=NOW)
        values["power_seller"] = Measured(None)
        missing = compute_trust("ml-v1", build_signals("ml-v1", values), stage="final", now=NOW)
        self.assertEqual(zero.score, 94)
        self.assertEqual(zero.coverage, 0.9)
        self.assertEqual(missing.score, 100)
        self.assertEqual(missing.coverage, 0.85)

        few = _ml_seller(level_id="1_red", power_seller_status=None, transactions={"completed": 9, "total": 9, "ratings": {"negative": 0.9}})
        quiet = score_mercadolibre(_ml_item(), few, description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertNotIn("Reputación roja con más de 10 ventas", quiet.red_flags)
        self.assertNotEqual(quiet.score, 0)
        thermometer = next(signal for signal in quiet.signals if signal.key == "thermometer")
        self.assertEqual(thermometer.value, 0)

        many = _ml_seller(level_id="1_red", transactions={"completed": 20, "total": 20, "ratings": {"negative": 0.04}})
        flagged = score_mercadolibre(_ml_item(), many, description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertIn("Reputación roja con más de 10 ventas", flagged.red_flags)
        self.assertEqual(flagged.score, 0)
        self.assertEqual(flagged.verdict, "riesgosa")

    def test_suspended_or_new_account_is_a_red_flag_only_when_closed(self):
        seller = _ml_seller()
        seller["status"] = {"site_status": "paused"}
        opened = score_mercadolibre(_ml_item(), seller, description=WORDS, now=NOW, stage="parcial")
        self.assertEqual(opened.stage, "parcial")
        self.assertIsNone(opened.score)
        self.assertIn("Cuenta de vendedor suspendida o inactiva", opened.red_flags)
        closed = score_mercadolibre(_ml_item(), seller, description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertEqual(closed.score, 0)
        fresh = _ml_seller()
        fresh["registration_date"] = "2026-10-10T00:00:00.000-04:00"
        recent = score_mercadolibre(_ml_item(), fresh, description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertIn("Cuenta creada hace menos de un mes", recent.red_flags)
        self.assertEqual(recent.score, 0)

    def test_warranty_can_come_from_sale_terms(self):
        item = _ml_item()
        item.pop("warranty")
        item["sale_terms"] = [{"id": "WARRANTY_TIME", "value_name": "6 meses"}]
        score = score_mercadolibre(item, _ml_seller(), description=WORDS, price_deviation=0, now=NOW, stage="final")
        warranty = next(signal for signal in score.signals if signal.key == "warranty")
        self.assertEqual(warranty.value, 1)
        self.assertIn("6 meses", warranty.reason or "")

    def test_negative_ratings_at_25_percent_are_a_flag(self):
        seller = _ml_seller(transactions={"completed": 40, "total": 40, "ratings": {"negative": 0.25}})
        score = score_mercadolibre(_ml_item(), seller, description=WORDS, price_deviation=0, now=NOW, stage="final")
        self.assertIn("25% o más de calificaciones negativas", score.red_flags)
        self.assertEqual(score.score, 0)


class AggregateTest(unittest.TestCase):
    def test_five_comparables_close_mercadolibre_and_four_do_not(self):
        trust = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, now=NOW)
        self.assertEqual(trust.signals[-2].value, "pending")  # price_anomaly
        offers = []
        merchants = []
        for index, price in enumerate((100, 100, 100, 100, 50)):
            merchant_id = f"ml:{index}"
            merchants.append(_merchant(merchant_id, "mercadolibre", f"https://example.com/{index}"))
            offers.append(_offer(f"o{index}", merchant_id, trust, price=price))
        result = aggregate(offers, merchants, now=NOW)
        self.assertEqual(len(result.price_stats), 1)
        self.assertEqual(result.price_stats[0].median_usd, 100)
        self.assertEqual(result.price_stats[0].comparables, 5)
        by_price = {offer.price_usd: offer for offer in result.offers}
        cheap = by_price[50]
        self.assertEqual(cheap.trust.stage, "final")
        self.assertEqual(cheap.trust.score, 0)
        self.assertIn(PRICE_RED_FLAG, cheap.trust.red_flags)
        self.assertTrue(all(signal.value != "pending" for signal in cheap.trust.signals))
        fair = by_price[100]
        self.assertEqual(fair.trust.verdict, "confiable")
        self.assertGreaterEqual(fair.trust.score or 0, 75)
        price_signal = next(signal for signal in fair.trust.signals if signal.key == "price_anomaly")
        self.assertEqual(price_signal.value, 1)

        short = aggregate(offers[:4], merchants[:4], now=NOW)
        self.assertEqual(short.price_stats, [])
        closed = short.offers[0]
        anomaly = next(signal for signal in closed.trust.signals if signal.key == "price_anomaly")
        self.assertIsNone(anomaly.value)
        self.assertNotIn(PRICE_RED_FLAG, closed.trust.red_flags)
        self.assertEqual(closed.trust.stage, "final")

    def test_a_used_listing_is_not_compared_with_new_ones(self):
        trust = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, now=NOW)
        offers = []
        merchants = []
        for index, price in enumerate((100, 100, 100, 100, 100)):
            merchant_id = f"ml:{index}"
            merchants.append(_merchant(merchant_id, "mercadolibre", f"https://example.com/n{index}"))
            offers.append(_offer(f"n{index}", merchant_id, trust, price=price))
        merchants.append(_merchant("ml:used", "mercadolibre", "https://example.com/used"))
        offers.append(_offer("used", "ml:used", trust, price=10, condition="usado"))
        result = aggregate(offers, merchants, now=NOW)
        used = next(offer for offer in result.offers if offer.id == "used")
        anomaly = next(signal for signal in used.trust.signals if signal.key == "price_anomaly")
        self.assertIsNone(anomaly.value)
        self.assertNotIn(PRICE_RED_FLAG, used.trust.red_flags)
        self.assertEqual(used.judge.comparables, 1)

    def test_passes_close_web_from_instagram_before_meta_ads(self):
        rif = [MerchantLink(kind="rif", value="J-12345678-9")]
        ig = _merchant("ig:bodegon", "instagram", "https://instagram.com/bodegon", links=rif)
        web = _merchant("web:tienda", "web", "https://tiendax.com.ve", links=rif)
        ig_trust = compute_trust("ig-v1", _uniform("ig-v1", 0.8, pending={"price_anomaly"}), stage="parcial", now=NOW)
        web_trust = compute_trust("web-v1", _uniform("web-v1", 0.8, pending={"price_anomaly", "linked_socials"}), stage="parcial", now=NOW)
        result = aggregate(
            [_offer("ig1", ig.id, ig_trust, price=80), _offer("web1", web.id, web_trust, price=90)],
            [ig, web],
            [AdjustmentBinding(Adjustment(source="meta-ads", penalty=15, reasons=["Anuncios muy cortos"]), merchant_id=ig.id)],
            now=NOW,
        )
        closed = {offer.id: offer for offer in result.offers}
        self.assertEqual(closed["ig1"].trust.score, 65)
        self.assertEqual(closed["ig1"].trust.verdict, "precaucion")
        linked = next(signal for signal in closed["web1"].trust.signals if signal.key == "linked_socials")
        self.assertEqual(linked.value, 0.8)
        self.assertEqual(closed["web1"].trust.score, 80)
        self.assertEqual(result.merchants[0].entity_id, result.merchants[1].entity_id)

    def test_a_one_way_link_does_not_feed_linked_socials(self):
        ig = _merchant("ig:bodegon", "instagram", "https://instagram.com/bodegon")
        web = _merchant(
            "web:tienda",
            "web",
            "https://tiendax.com.ve",
            links=[MerchantLink(kind="instagram", value="bodegon")],
        )
        ig_trust = compute_trust("ig-v1", _uniform("ig-v1", 0.8, pending={"price_anomaly"}), stage="parcial", now=NOW)
        web_trust = compute_trust("web-v1", _uniform("web-v1", 0.8, pending={"price_anomaly", "linked_socials"}), stage="parcial", now=NOW)
        result = aggregate(
            [_offer("ig1", ig.id, ig_trust), _offer("web1", web.id, web_trust, price=90)],
            [ig, web],
            now=NOW,
        )
        identities = {merchant.id: merchant.entity_id for merchant in result.merchants}
        self.assertNotEqual(identities["ig:bodegon"], identities["web:tienda"])
        linked = next(signal for signal in result.offers[1].trust.signals if signal.key == "linked_socials")
        self.assertIsNone(linked.value)
        self.assertTrue(any(item.confidence == 0.6 and item.method == "declarado" for item in result.candidates))

    def test_copied_photos_are_a_flag_when_the_count_is_known(self):
        merchant = _merchant("fb:1", "facebook", "https://facebook.com/marketplace/item/1")
        trust = compute_trust("fb-v1", _uniform("fb-v1", 1, pending={"photos_original", "price_anomaly"}), stage="parcial", now=NOW)
        offer = _offer("photo", merchant.id, trust)
        copied = aggregate([offer], [merchant], photos_seen_elsewhere={"photo": 2}, now=NOW)
        self.assertEqual(copied.offers[0].trust.score, 0)
        self.assertIn("Varias fotos copiadas de otros vendedores", copied.offers[0].trust.red_flags)
        own = aggregate([offer], [merchant], photos_seen_elsewhere={"photo": 0}, now=NOW)
        photo = next(signal for signal in own.offers[0].trust.signals if signal.key == "photos_original")
        self.assertEqual(photo.value, 1)
        self.assertEqual(own.offers[0].trust.score, 100)
        unknown = aggregate([offer], [merchant], now=NOW)
        missing = next(signal for signal in unknown.offers[0].trust.signals if signal.key == "photos_original")
        self.assertIsNone(missing.value)
        self.assertEqual(unknown.offers[0].trust.verdict, "confiable")

    def test_evidence_outside_the_offer_is_dropped(self):
        merchant = _merchant("ml:1", "mercadolibre", "https://example.com/1")
        trust = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, now=NOW)
        bad_signals = list(trust.signals)
        bad_signals[0] = bad_signals[0].model_copy(update={"evidence_id": "missing"})
        bad = _offer("bad", merchant.id, trust.model_copy(update={"signals": bad_signals}))
        good = _offer("good", merchant.id, trust, price=80)
        result = aggregate([bad, good], [merchant], now=NOW)
        self.assertEqual([offer.id for offer in result.offers], ["good"])
        self.assertEqual(result.dropped[0].code, "parseo")
        self.assertEqual(result.dropped[0].offer_id, "bad")

    def test_source_data_does_not_change_the_score(self):
        trust = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, price_deviation=0, now=NOW, stage="final")
        left = _merchant("ml:1", "mercadolibre", "https://example.com/1", source_data={"raw": {"level": "5_green"}})
        right = _merchant("ml:1", "mercadolibre", "https://example.com/1", source_data={"raw": {"level": "1_red"}})
        a = aggregate([_offer("a", left.id, trust)], [left], now=NOW)
        b = aggregate([_offer("a", right.id, trust)], [right], now=NOW)
        self.assertEqual(a.offers[0].trust.model_dump(), b.offers[0].trust.model_dump())
        self.assertNotEqual(a.merchants[0].source_data, b.merchants[0].source_data)

    def test_card_hides_signals_and_keeps_three_reasons(self):
        signals = [
            TrustSignal(family="precio", key="heavy", weight=70, value=0, reason="grave"),
            TrustSignal(family="riesgo", key="mid", weight=20, value=0.2, reason="media"),
            TrustSignal(family="identidad", key="light", weight=10, value=0.9, reason="leve"),
        ]
        trust = compute_trust("custom-v1", signals, stage="final", red_flags=["bandera"], now=NOW)
        merchant = _merchant("ig:1", "instagram", "https://instagram.com/bodegon", location=None)
        offer = _offer("a", merchant.id, trust)
        offer = offer.model_copy(
            update={"rate_used": RateRef(source="BCV", usd_to_ves=200, observed_at=NOW), "price_usd": 100}
        )
        card = to_card(offer, merchant, rank=1, is_example=False)
        dumped = card.model_dump()
        self.assertNotIn("signals", dumped)
        self.assertEqual(card.trust_reasons, ["bandera", "grave", "media"])
        self.assertEqual(card.trust_stars, 0)
        self.assertEqual(card.trust_verdict, "riesgosa")
        self.assertIn("BCV", card.rate_note or "")
        self.assertIn("USD", card.price_display or "")

    def test_close_listings_leaves_todays_cards_and_closes_a_contract_offer(self):
        card = {"title": "A", "url": "https://example.com/a", "trust": 70}
        original = dict(card)
        self.assertEqual(close_listings([card]), [card])
        self.assertEqual(card, original)
        trust = score_mercadolibre(_ml_item(), _ml_seller(), description=WORDS, now=NOW)
        merchant = _merchant("ml:9", "mercadolibre", "https://example.com/9")
        offer = _offer("ml-offer", merchant.id, trust, price=120)
        listing = {
            "title": offer.title,
            "url": offer.url,
            "trust": 40,
            "contractOffer": offer.model_dump(mode="json", by_alias=True),
            "contractMerchant": merchant.model_dump(mode="json", by_alias=True),
        }
        closed = close_listings([listing])[0]
        self.assertEqual(closed["trust"]["stage"], "final")
        self.assertEqual(closed["trustStars"], 5)
        self.assertNotIn("trustError", closed)
        broken = close_listings([{"contractOffer": {"id": "nope"}, "contractMerchant": {"id": "nope"}}])[0]
        self.assertEqual(broken["trustError"], "parseo")


class IdentityTest(unittest.TestCase):
    def test_rif_phone_domain_and_mutual_links(self):
        a = _merchant("ig:a", "instagram", "https://instagram.com/a", links=[MerchantLink(kind="rif", value="j-12345678-9")])
        b = _merchant("web:b", "web", "https://www.TiendaX.com.ve/inicio", links=[MerchantLink(kind="rif", value="J123456789")])
        identities, candidates = resolve_identities([a, b])
        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0].method, "rif")
        self.assertEqual(identities[0].confidence, 1)
        self.assertEqual(identities[0].members, ["ig:a", "web:b"])
        self.assertEqual(identities[0].entity_id, entity_id_for("rif:J123456789"))
        self.assertEqual(candidates, [])

        left = _merchant("ig:1", "instagram", "https://instagram.com/bodegon", links=[MerchantLink(kind="whatsapp", value="0412-555-1234")])
        right = _merchant("tt:1", "tiktok", "https://www.tiktok.com/@otro", links=[MerchantLink(kind="whatsapp", value="04125551234")])
        phone, _weak = resolve_identities([left, right])
        self.assertEqual(phone[0].method, "telefono")
        self.assertEqual(phone[0].confidence, 0.8)

        shop = _merchant("web:1", "web", "https://www.TiendaX.com.ve/a")
        shop2 = _merchant("web:2", "web", "https://tiendax.com.ve")
        domain, _weak = resolve_identities([shop, shop2])
        self.assertEqual(domain[0].method, "dominio")
        self.assertEqual(domain[0].confidence, 0.9)
        self.assertEqual(domain[0].entity_id, entity_id_for("dominio:tiendax.com.ve"))

        ig = _merchant("ig:bodegon", "instagram", "https://instagram.com/bodegon", links=[MerchantLink(kind="tiktok", value="bodegon")])
        tt = _merchant("tt:bodegon", "tiktok", "https://www.tiktok.com/@bodegon", links=[MerchantLink(kind="instagram", value="@bodegon")])
        mutual, weak = resolve_identities([ig, tt])
        self.assertEqual(mutual[0].method, "declarado")
        self.assertEqual(mutual[0].confidence, 0.9)
        self.assertEqual(weak, [])

    def test_handle_and_one_way_link_stay_apart(self):
        ig = _merchant("ig:ventasve", "instagram", "https://instagram.com/ventasve")
        tt = _merchant("tt:ventasve", "tiktok", "https://www.tiktok.com/@ventasve")
        identities, candidates = resolve_identities([ig, tt])
        self.assertEqual(len(identities), 2)
        self.assertTrue(any(item.method == "handle" and item.confidence == 0.5 for item in candidates))

        web = _merchant("web:tienda", "web", "https://tiendax.com.ve", links=[MerchantLink(kind="instagram", value="ventasve")])
        apart, weak = resolve_identities([ig, web])
        self.assertEqual(len(apart), 2)
        self.assertTrue(any(item.method == "declarado" and item.confidence == 0.6 for item in weak))

    def test_a_weaker_link_does_not_override_the_rif(self):
        a = _merchant("ig:a", "instagram", "https://instagram.com/a", links=[MerchantLink(kind="rif", value="J-12345678-9"), MerchantLink(kind="whatsapp", value="04141234567")])
        b = _merchant("web:b", "web", "https://b.com", links=[MerchantLink(kind="rif", value="J123456789")])
        c = _merchant("tt:c", "tiktok", "https://www.tiktok.com/@c", links=[MerchantLink(kind="whatsapp", value="04141234567")])
        identities, _candidates = resolve_identities([a, b, c])
        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0].method, "rif")
        self.assertEqual(identities[0].members, ["ig:a", "tt:c", "web:b"])


def _measured(*pairs: tuple[str, float]) -> list[TrustSignal]:
    wanted = dict(pairs)
    values = {spec.key: Measured(1.0 if spec.key in wanted else None) for spec in CATALOGS["ml-v1"]}
    return build_signals("ml-v1", values)


if __name__ == "__main__":
    unittest.main()
