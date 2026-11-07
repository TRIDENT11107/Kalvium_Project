from modules.lesson_generator import generate_lesson

class LessonGenerationService:
    def generate(self, title: str, objective: str, sources: list[dict]) -> dict:
        return generate_lesson(title, objective, sources)
