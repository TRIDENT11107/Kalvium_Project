from utils.llm_client import generate_json
from utils.prompt_compaction import compact_json
from config import GROQ_QC_MAX_COMPLETION_TOKENS


CRITERION_WEIGHTS = {
    "claim_accuracy": 0.40,
    "evidence_completeness": 0.25,
    "source_reliability": 0.20,
    "consistency": 0.15,
}


def _bounded(value, default=50):
    try:
        return max(0, min(100, float(value)))
    except (TypeError, ValueError):
        return default


def calculate_factual_score(criteria, issues=None, has_evidence=True):
    """Return a weighted, explainable score from independent 0-100 criteria."""
    values = {name: _bounded(criteria.get(name), 50) for name in CRITERION_WEIGHTS}
    issues = issues or []
    unsupported = sum(1 for issue in issues if str(issue.get("classification", "")).lower() == "unsupported")
    false_claims = sum(1 for issue in issues if str(issue.get("classification", "")).lower() == "false")
    values["evidence_completeness"] = max(0, values["evidence_completeness"] - unsupported * 5)
    values["claim_accuracy"] = max(0, values["claim_accuracy"] - false_claims * 10)
    if not has_evidence:
        values["evidence_completeness"] = min(values["evidence_completeness"], 20)
        values["source_reliability"] = min(values["source_reliability"], 20)
    score = round(sum(values[name] * weight for name, weight in CRITERION_WEIGHTS.items()))
    return score, values


def normalize_factual_report(report):
    """Validate an LLM report and add a mathematically consistent score breakdown."""
    if not isinstance(report, dict):
        raise ValueError("Factual QC returned a non-object response.")
    issues = report.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("Factual QC issues must be an array.")
    criteria = report["score_breakdown"] if "score_breakdown" in report else report.get("criteria", {})
    if not isinstance(criteria, dict):
        raise ValueError("Factual QC score breakdown must be an object.")
    score, values = calculate_factual_score(criteria, issues, has_evidence=bool(report.get("evidence_available", True)))
    if not criteria and "score" in report:
        score = round(_bounded(report["score"]))
    classifications = {"unsupported": 0, "false": 0}
    for issue in issues:
        if isinstance(issue, dict):
            classification = str(issue.get("classification", "")).lower()
            if classification in classifications:
                classifications[classification] += 1
    result = dict(report)
    result["score"] = score
    result["issue_count"] = len(issues)
    result["score_breakdown"] = values
    result["score_explanation"] = (
        "Weighted score: claim accuracy 40%, evidence completeness 25%, "
        "source reliability 20%, and consistency 15%. Unsupported claims "
        "reduce evidence completeness; demonstrably false claims reduce claim accuracy."
    )
    result["claim_classifications"] = classifications
    return result


def run_factual_qc(lesson, sources):
    evidence = [{
        "type": source.get("type"),
        "title": source.get("title"),
        "url": source.get("url"),
        "description": (source.get("description") or "")[:220],
        "doi": source.get("doi"),
        "published": source.get("published"),
    } for source in sources]
    system = (
        "You are an independent factual accuracy evaluator. You receive only lesson "
        "content and research evidence. Do not assess teaching quality and do not "
        "assume evidence exists. Return JSON only."
    )
    prompt = (
        "Evaluate correctness, unsupported or misleading claims, source reliability "
        "and relevance, missing evidence, gaps, contradictions, and whether claims "
        "are supported. Distinguish an unsupported claim (no retrieved evidence) "
        "from a false claim (evidence contradicts it); do not treat source "
        "reliability as claim accuracy. Be concise: return at most 3 highest-priority "
        "issues, with one or two sentences per explanation. Return score_breakdown "
        "with claim_accuracy, evidence_completeness, source_reliability, and "
        "consistency, each 0-100, plus evidence_available (true only when usable "
        "evidence was supplied). The final score must be their weighted average "
        "(40%, 25%, 20%, 15%) before the explicit issue penalties. Also return counts, recommended_improvements, and "
        "issues. Each issue must contain id, section, claim, classification "
        "(unsupported or false), severity, explanation, evidence, suggested_correction, "
        "confidence. Lesson=" +
        compact_json(lesson, string_limit=300, item_limit=5, key_limit=8) +
        " Evidence=" + compact_json(evidence, string_limit=160, item_limit=16, key_limit=7)
    )
    response = generate_json(system, prompt, max_completion_tokens=GROQ_QC_MAX_COMPLETION_TOKENS)
    return normalize_factual_report(response)
