"""
Tests for the deterministic ranker.

No mocking needed — pure Python arithmetic.
"""

import pytest
from backend.schemas.event import Magnitude, TimeHorizon
from backend.schemas.impact import ImpactCandidate, ImpactOrder
from backend.services.ranker import rank, score_candidate, _W_ORDER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candidate(
    ticker="TSM",
    impact_direction="bullish",
    impact_order=ImpactOrder.DIRECT,
    confidence=0.80,
    priced_in_assessment=0.20,
    tradability_score=0.80,
    final_score=0.0,
    relationship_type="foundry_customer",
    mechanism="Test mechanism.",
    time_horizon=TimeHorizon.WEEKS,
) -> ImpactCandidate:
    return ImpactCandidate(
        ticker=ticker,
        company_name=ticker,
        impact_direction=impact_direction,
        impact_order=impact_order,
        relationship_type=relationship_type,
        mechanism=mechanism,
        confidence=confidence,
        time_horizon=time_horizon,
        priced_in_assessment=priced_in_assessment,
        tradability_score=tradability_score,
        final_score=final_score,
    )


# ---------------------------------------------------------------------------
# score_candidate
# ---------------------------------------------------------------------------

class TestScoreCandidate:
    def test_returns_new_object_not_mutated(self):
        c = make_candidate()
        scored = score_candidate(c, Magnitude.HIGH)
        assert c.final_score == 0.0          # original unchanged
        assert scored.final_score > 0.0

    def test_final_score_in_range(self):
        for order in ImpactOrder:
            for mag in Magnitude:
                c = make_candidate(impact_order=order)
                scored = score_candidate(c, mag)
                assert 0.0 <= scored.final_score <= 1.0, (
                    f"Out of range for order={order}, mag={mag}: {scored.final_score}"
                )

    def test_direct_scores_higher_than_second_order(self):
        direct = make_candidate(impact_order=ImpactOrder.DIRECT)
        second = make_candidate(impact_order=ImpactOrder.SECOND_ORDER)
        assert score_candidate(direct, Magnitude.HIGH).final_score > \
               score_candidate(second, Magnitude.HIGH).final_score

    def test_second_order_scores_higher_than_third_order(self):
        second = make_candidate(impact_order=ImpactOrder.SECOND_ORDER)
        third = make_candidate(impact_order=ImpactOrder.THIRD_ORDER)
        assert score_candidate(second, Magnitude.HIGH).final_score > \
               score_candidate(third, Magnitude.HIGH).final_score

    def test_higher_confidence_raises_score(self):
        low = make_candidate(confidence=0.40)
        high = make_candidate(confidence=0.90)
        assert score_candidate(high, Magnitude.HIGH).final_score > \
               score_candidate(low, Magnitude.HIGH).final_score

    def test_high_priced_in_lowers_score(self):
        fresh = make_candidate(priced_in_assessment=0.05)
        stale = make_candidate(priced_in_assessment=0.90)
        assert score_candidate(fresh, Magnitude.HIGH).final_score > \
               score_candidate(stale, Magnitude.HIGH).final_score

    def test_critical_magnitude_gives_higher_score_than_low(self):
        c = make_candidate()
        critical = score_candidate(c, Magnitude.CRITICAL)
        low = score_candidate(c, Magnitude.LOW)
        assert critical.final_score > low.final_score

    def test_zero_confidence_produces_low_but_nonnegative_score(self):
        c = make_candidate(confidence=0.0, tradability_score=0.0)
        scored = score_candidate(c, Magnitude.LOW)
        assert scored.final_score >= 0.0

    def test_perfect_candidate_scores_close_to_one(self):
        c = make_candidate(
            impact_order=ImpactOrder.DIRECT,
            confidence=1.0,
            tradability_score=1.0,
            priced_in_assessment=0.0,
        )
        scored = score_candidate(c, Magnitude.CRITICAL)
        assert scored.final_score > 0.90

    def test_score_rounded_to_4_decimal_places(self):
        c = make_candidate()
        scored = score_candidate(c, Magnitude.HIGH)
        assert scored.final_score == round(scored.final_score, 4)


# ---------------------------------------------------------------------------
# rank
# ---------------------------------------------------------------------------

class TestRank:
    def test_returns_sorted_descending(self):
        candidates = [
            make_candidate("A", impact_order=ImpactOrder.THIRD_ORDER, confidence=0.5),
            make_candidate("B", impact_order=ImpactOrder.DIRECT, confidence=0.9),
            make_candidate("C", impact_order=ImpactOrder.SECOND_ORDER, confidence=0.7),
        ]
        ranked = rank(candidates, Magnitude.HIGH)
        scores = [c.final_score for c in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_top_candidate_is_highest_score(self):
        candidates = [
            make_candidate("X", impact_order=ImpactOrder.THIRD_ORDER, confidence=0.4),
            make_candidate("Y", impact_order=ImpactOrder.DIRECT, confidence=0.95),
        ]
        ranked = rank(candidates, Magnitude.HIGH)
        assert ranked[0].ticker == "Y"

    def test_empty_list_returns_empty(self):
        assert rank([], Magnitude.HIGH) == []

    def test_single_candidate_returned_unchanged_structure(self):
        c = make_candidate()
        ranked = rank([c], Magnitude.HIGH)
        assert len(ranked) == 1
        assert ranked[0].ticker == "TSM"

    def test_input_not_mutated(self):
        c = make_candidate()
        original_score = c.final_score
        rank([c], Magnitude.HIGH)
        assert c.final_score == original_score   # original object untouched

    def test_all_final_scores_populated(self):
        candidates = [make_candidate(str(i)) for i in range(5)]
        ranked = rank(candidates, Magnitude.MEDIUM)
        assert all(c.final_score > 0.0 for c in ranked)

    def test_magnitude_affects_all_scores(self):
        candidates = [make_candidate("T")]
        high_scores = [c.final_score for c in rank(candidates, Magnitude.HIGH)]
        low_scores  = [c.final_score for c in rank(candidates, Magnitude.LOW)]
        assert all(h > l for h, l in zip(high_scores, low_scores))

    def test_priced_in_penalty_applied_in_ranking(self):
        # Within the same impact order, a fresh catalyst outranks a fully-priced-in one
        fresh = make_candidate("F", priced_in_assessment=0.0,
                               impact_order=ImpactOrder.DIRECT)
        stale = make_candidate("S", priced_in_assessment=0.95,
                               impact_order=ImpactOrder.DIRECT)
        ranked = rank([stale, fresh], Magnitude.HIGH)
        assert ranked[0].ticker == "F"

    def test_fresh_second_order_beats_stale_direct(self):
        # Product behavior: a fully-priced-in direct name should lose to a
        # credible second-order name that the market has not yet discounted.
        # priced_in weight (0.25) is equal to order weight (0.25), so the
        # priced-in penalty can overcome the order advantage when the gap is large.
        direct_stale  = make_candidate("D", priced_in_assessment=0.95,
                                       impact_order=ImpactOrder.DIRECT)
        second_fresh  = make_candidate("S", priced_in_assessment=0.0,
                                       impact_order=ImpactOrder.SECOND_ORDER)
        ranked = rank([direct_stale, second_fresh], Magnitude.HIGH)
        assert ranked[0].ticker == "S"
