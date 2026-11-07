from celery import Celery
from app.settings import settings
celery_app=Celery("lesson_studio",broker=settings.redis_url,backend=settings.redis_url,include=["app.tasks.pipeline"])
celery_app.conf.update(task_track_started=True,task_serializer="json",result_serializer="json",accept_content=["json"],task_acks_late=True,worker_prefetch_multiplier=1)
