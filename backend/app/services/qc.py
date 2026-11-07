from modules.factual_qc import run_factual_qc
from modules.instructional_qc import run_instructional_qc

class FactualQCService:
    def audit(self, lesson: dict, sources: list[dict]) -> dict:
        return run_factual_qc(lesson, sources)
class InstructionalQCService:
    def audit(self, lesson: dict, objective: str, *, title: str = "", structure: dict | None = None) -> dict:
        return run_instructional_qc(lesson, title=title, objective=objective, structure=structure)
