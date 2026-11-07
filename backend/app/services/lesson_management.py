from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Lesson

class LessonManagementService:
    def get_owned(self, db: Session, lesson_id: int, owner_id: int) -> Lesson:
        lesson=db.get(Lesson,lesson_id)
        if lesson is None or lesson.owner_id != owner_id:
            raise HTTPException(404,"Lesson not found")
        return lesson
