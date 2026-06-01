# Quality Evaluation Report

**Date**: 2026-05-31 17:03 UTC | **Exam**: test-exam | **Mode**: autonomous

## Summary

| Component | Metrics | PASS | WARN | FAIL | SKIP |
|---|---|---|---|---|---|
| BKT | 5 | 2 | 1 | 2 | 0 |
| FSRS | 3 | 2 | 0 | 1 | 0 |
| Recommender | 6 | 0 | 0 | 0 | 6 |
| Explanation (RAG) | 3 | 0 | 0 | 1 | 2 |
| Theme Summary | 3 | 0 | 0 | 2 | 1 |
| **Total** | **20** | **4** | **1** | **6** | **9** |

## BKT

| Metric | Value | Good Threshold | Critical | Status |
|---|---|---|---|---|
| Monotonicity (correct) | 0.1198 | 0.0010 | 0.0000 | ✅ PASS |
| Monotonicity (incorrect) | -0.1173 | -0.0010 | 0.0000 | ✅ PASS |
| AUC-ROC | 0.4474 | 0.7500 | 0.6000 | ❌ FAIL |
| Log-Loss | 0.9480 | 0.6000 | 0.8000 | ❌ FAIL |
| RMSE | 0.5741 | 0.4000 | 0.6000 | ⚠️ WARN |

**Interpretation:**

- **Monotonicity (correct)**: P(L) should increase after correct answers. Average ΔP(L) = +0.119773
- **Monotonicity (incorrect)**: P(L) should decrease after incorrect answers. Average ΔP(L) = -0.117315
- **AUC-ROC**: AUC ≥ 0.75: BKT is informative. 0.60–0.75: weak, parameters not calibrated. < 0.60: equivalent to random guessing.
- **Log-Loss**: Log-Loss < 0.60: good calibration. > 0.80: predictions are overconfident or wrong.
- **RMSE**: Root Mean Square Error of P(correct) vs actual. < 0.40: good. 0.40–0.60: acceptable. > 0.60: poor predictions.

## FSRS

| Metric | Value | Good Threshold | Critical | Status |
|---|---|---|---|---|
| Stability monotonicity (correct) | 9021.6600 | 0.0010 | 0.0000 | ✅ PASS |
| Stability monotonicity (incorrect) | -11537.7200 | -0.0010 | 0.0000 | ✅ PASS |
| Calibration ECE | 0.3433 | 0.0500 | 0.1000 | ❌ FAIL |

**Interpretation:**

- **Stability monotonicity (correct)**: Memory stability should increase after correct answers. Average ΔS = +9021.66s
- **Stability monotonicity (incorrect)**: Memory stability should decrease after incorrect answers. Average ΔS = -11537.72s
- **Calibration ECE**: ECE < 0.05: excellent calibration. 0.05–0.10: acceptable. > 0.10: FSRS constants need calibration.

## Recommender

| Metric | Value | Good Threshold | Critical | Status |
|---|---|---|---|---|
| ECE (calibration) | — | 0.0500 | 0.1000 | ⏭️ SKIP |
| Brier Score | — | 0.2500 | 0.4000 | ⏭️ SKIP |
| Hit Rate@5 | — | 0.3000 | 0.1000 | ⏭️ SKIP |
| NDCG@5 | — | 0.4000 | 0.2000 | ⏭️ SKIP |
| Topic Coverage | — | 0.6000 | 0.3000 | ⏭️ SKIP |
| Filter consistency | — | 1.0000 | 0.5000 | ⏭️ SKIP |

**Interpretation:**

- **ECE (calibration)**: ECE < 0.05: expected_p_correct is well-calibrated. > 0.10: BKT parameters need fitting.
- **Brier Score**: Brier Score < 0.25: good predictions. > 0.40: predictions are poor.
- **Hit Rate@5**: Hit Rate ≥ 0.30: recommendations are relevant. < 0.10: revise scoring weights or loosen filters.
- **NDCG@5**: NDCG ≥ 0.40: good ranking. < 0.20: ranking is nearly random.
- **Topic Coverage**: Coverage ≥ 0.60: good diversity. < 0.30: recommender is stuck on one topic.
- **Filter consistency**: All recommendations should respect cooldown and mastered filters.

## Explanation (RAG)

| Metric | Value | Good Threshold | Critical | Status |
|---|---|---|---|---|
| Structure Compliance | 0.5000 | 0.9500 | 0.9000 | ❌ FAIL |
| Faithfulness (LLM-judge) | — | 0.9000 | 0.7000 | ⏭️ SKIP |
| Answer Relevancy (LLM-judge, 1-5) | — | 4.0000 | 3.0000 | ⏭️ SKIP |

**Interpretation:**

- **Structure Compliance**: ≥ 0.95: explanations have all 4 required sections. < 0.90: prompt needs stricter formatting instructions.
- **Faithfulness (LLM-judge)**: ≥ 0.90: explanations are grounded in context. < 0.70: LLM is hallucinating facts.
- **Answer Relevancy (LLM-judge, 1-5)**: ≥ 4.0: explanations address the student's error well. < 3.0: retrieval or prompt issues.

## Theme Summary

| Metric | Value | Good Threshold | Critical | Status |
|---|---|---|---|---|
| Format Compliance | 0.6000 | 0.9500 | 0.9000 | ❌ FAIL |
| Concept Coverage | 0.0000 | 0.7000 | 0.5000 | ❌ FAIL |
| Faithfulness (LLM-judge) | — | 0.8500 | 0.7000 | ⏭️ SKIP |

**Interpretation:**

- **Format Compliance**: ≥ 0.95: summaries meet format requirements. < 0.90: prompt needs adjustment.
- **Concept Coverage**: ≥ 0.70: summaries cover most key concepts. < 0.50: prompt needs to emphasize mentioning all terms.
- **Faithfulness (LLM-judge)**: ≥ 0.85: summaries don't hallucinate. < 0.70: summaries contain fabricated facts.

## Action Items

- **[BKT] AUC-ROC**: AUC ≥ 0.75: BKT is informative. 0.60–0.75: weak, parameters not calibrated. < 0.60: equivalent to random guessing.
- **[BKT] Log-Loss**: Log-Loss < 0.60: good calibration. > 0.80: predictions are overconfident or wrong.
- **[FSRS] Calibration ECE**: ECE < 0.05: excellent calibration. 0.05–0.10: acceptable. > 0.10: FSRS constants need calibration.
- **[Explanation (RAG)] Structure Compliance**: ≥ 0.95: explanations have all 4 required sections. < 0.90: prompt needs stricter formatting instructions.
- **[Theme Summary] Format Compliance**: ≥ 0.95: summaries meet format requirements. < 0.90: prompt needs adjustment.
- **[Theme Summary] Concept Coverage**: ≥ 0.70: summaries cover most key concepts. < 0.50: prompt needs to emphasize mentioning all terms.

---
*Report generated by evaluation module — kn-trace-itmo*
