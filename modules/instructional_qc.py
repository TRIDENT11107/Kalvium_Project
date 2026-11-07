from utils.llm_client import generate_json
from utils.prompt_compaction import compact_json
from config import GROQ_QC_MAX_COMPLETION_TOKENS


def run_instructional_qc(lesson, title=None, objective=None, structure=None):
    lesson_design = structure if structure is not None else lesson
    system = (
        "You are an independent instructional quality evaluator. You receive no "
        "research evidence and must not evaluate factual correctness. Return JSON only."
    )
    prompt = (
        "Evaluate objective alignment, clarity, logical sequence, readability, "
        "examples, practical applications, activities, knowledge checks, missing "
        "prerequisites, and whether the lesson fits 45 minutes. Be concise: return "
        "at most 3 highest-priority issues, with one or two sentences per explanation. Return score, "
        "alignment_score, clarity_score, structure_score, practical_relevance_score, "
        "assessment_quality_score, time_assessment, gaps, recommended_improvements, "
        "and issues. Each issue must contain id, section, issue, explanation, "
        "suggested_improvement, confidence, severity. Title=" + str(title) +
        " Objective=" + str(objective) + " Lesson design=" +
        compact_json(lesson_design, string_limit=300, item_limit=6, key_limit=8)
    )
    return generate_json(system, prompt, max_completion_tokens=GROQ_QC_MAX_COMPLETION_TOKENS)
