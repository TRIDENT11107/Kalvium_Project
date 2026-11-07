import os, sys, json, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
root=str(Path(__file__).resolve().parents[3])
if root not in sys.path: sys.path.insert(0,root)
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Lesson,ResearchSource,QCReport,BackgroundTask,LessonSection,QCIssue,LessonRevision
from app.services.research import ResearchService
from app.services.generation import LessonGenerationService
from app.services.qc import FactualQCService,InstructionalQCService
from utils.llm_client import LLMError, GroqRateLimitError
from utils.lesson_validation import validate_lesson_duration


def save_sections(db,lesson,data):
    db.query(LessonSection).filter_by(lesson_id=lesson.id).delete()
    excluded={"time_plan","duration_minutes"}
    for index,(key,value) in enumerate(data.items()):
        if key in excluded: continue
        db.add(LessonSection(lesson_id=lesson.id,section_key=key,title=key.replace("_"," ").title(),content=value,order_index=index))

def save_report(db,lesson,kind,data,execution_id):
    issues=data.get("issues",[])
    for index,issue in enumerate(issues):
        if not issue.get("id"): issue["id"]=kind+"-"+str(index+1)
    report=db.query(QCReport).filter_by(
        lesson_id=lesson.id,kind=kind,execution_id=execution_id
    ).one_or_none()
    if report is None:
        report=QCReport(lesson_id=lesson.id,kind=kind,execution_id=execution_id)
        db.add(report); db.flush()
    report.score=float(data.get("score",0)); report.report=data
    db.query(QCIssue).filter_by(report_id=report.id).delete()
    for issue in issues:
        db.add(QCIssue(report_id=report.id,issue_key=kind+":"+str(issue.get("id")),
                       section=str(issue.get("section","")),
                       severity=str(issue.get("severity","Medium")),issue_data=issue))
    db.commit()

def update_task(db,task,status,progress,message,error=None):
    task.status=status; task.progress=progress; task.message=message; task.error=error; db.commit()

def transient_provider_error(error):
    message=str(error).lower()
    return isinstance(error, GroqRateLimitError) or isinstance(error,(TimeoutError,ConnectionError)) or (
        isinstance(error,LLMError) and any(marker in message for marker in (
            "failed", "timed out", "rate limit", "http 5"
        ))
    )

def save_sources(db,lesson,sources):
    db.query(ResearchSource).filter_by(lesson_id=lesson.id).delete()
    for s in sources:
        meta={k:v for k,v in s.items() if k not in ("type","title","url","description")}
        db.add(ResearchSource(lesson_id=lesson.id,kind=s.get("type","Website"),title=s.get("title","Source"),url=s.get("url",""),description=s.get("description",""),metadata_json=meta))

@celery_app.task(name="app.tasks.pipeline.generate_lesson_task",bind=True,max_retries=2,default_retry_delay=10)
def generate_lesson_task(self,task_id,lesson_id):
    db=SessionLocal()
    lesson=None
    phase="research"
    try:
        task=db.get(BackgroundTask,task_id); lesson=db.get(Lesson,lesson_id)
        if not task or not lesson: return
        lesson.research_status="running"; lesson.generation_status="queued"
        db.commit()
        research=ResearchService().collect(lesson.title,lesson.objective)
        if not research["all"]:
            raise RuntimeError("No research sources available: "+str(research["errors"]))
        lesson.research_status="partial" if research.get("partial") else "completed"
        save_sources(db,lesson,research["all"]); db.commit()
        update_task(db,task,"running",30,"Generating a source-grounded lesson")
        phase="generation"
        lesson.generation_status="running"; db.commit()
        generated=LessonGenerationService().generate(lesson.title,lesson.objective,research["all"])
        validate_lesson_duration(generated)
        lesson.lesson=generated; lesson.status="review"
        lesson.generation_status="completed"
        db.add(LessonRevision(lesson_id=lesson.id,lesson=generated,title=lesson.title,objective=lesson.objective,audience=lesson.audience,difficulty=lesson.difficulty,status="review",note="Generated lesson"))
        save_sections(db,lesson,generated); db.commit()
        phase="qc"
        lesson.factual_qc_status="running"; lesson.instructional_qc_status="running"; db.commit()
        results, failures = {}, {}
        active_kind=None
        def run_factual(): return FactualQCService().audit(generated, research["all"])
        def run_instructional():
            return InstructionalQCService().audit(
                generated, lesson.objective, title=lesson.title, structure=generated
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={"factual":pool.submit(run_factual),"instructional":pool.submit(run_instructional)}
            for kind,future in futures.items():
                try: results[kind]=future.result()
                except Exception as exc: failures[kind]=str(exc)
        for kind,data in results.items():
            active_kind=kind
            save_report(db,lesson,kind,data,task_id)
            setattr(lesson,kind+"_qc_status","completed")
        for kind in failures:
            setattr(lesson,kind+"_qc_status","failed")
        db.commit()
        if failures:
            update_task(db,task,"failed",100,"Lesson saved; one or more QC reports failed",
                        "; ".join(k+": "+v for k,v in failures.items()))
        else:
            update_task(db,task,"completed",100,"Lesson saved; both independent audit reports are ready")
    except Exception as exc:
        db.rollback()
        task=db.get(BackgroundTask,task_id)
        transient=transient_provider_error(exc)
        if transient and self.request.retries < self.max_retries:
            if task:
                lesson=db.get(Lesson,lesson_id)
                if lesson:
                    if phase=="research":
                        lesson.research_status="queued"
                    elif phase=="generation":
                        lesson.generation_status="queued"
                    db.commit()
                update_task(db,task,"queued",task.progress,"Temporary provider error; retrying")
            raise self.retry(exc=exc,countdown=max(1, int(getattr(exc, "retry_after", 10) or 10)))
        if task:
            lesson=db.get(Lesson,lesson_id)
            if lesson:
                if phase=="research":
                    lesson.research_status="failed"
                elif phase=="generation":
                    lesson.generation_status="failed"
                else:
                    if active_kind:
                        setattr(lesson,active_kind+"_qc_status","failed")
                    else:
                        lesson.factual_qc_status="failed"
                        lesson.instructional_qc_status="failed"
                db.commit()
            update_task(db,task,"failed",task.progress,
                        "Quality control failed" if phase=="qc" else "Generation failed",str(exc))
    finally: db.close()

@celery_app.task(name="app.tasks.pipeline.qc_task",bind=True,max_retries=2,default_retry_delay=10)
def qc_task(self,task_id,lesson_id,kind):
    db=SessionLocal()
    try:
        task=db.get(BackgroundTask,task_id); lesson=db.get(Lesson,lesson_id)
        if not task or not lesson: return
        update_task(db,task,"running",20,"Running "+kind+" quality control")
        sources=[{"type":s.kind,"title":s.title,"url":s.url,"description":s.description,**(s.metadata_json or {})} for s in lesson.sources]
        result=FactualQCService().audit(lesson.lesson,sources) if kind=="factual" else InstructionalQCService().audit(
            lesson.lesson, lesson.objective, title=lesson.title, structure=lesson.lesson
        )
        save_report(db,lesson,kind,result,task_id); update_task(db,task,"completed",100,kind+" report ready")
        setattr(lesson,kind+"_qc_status","completed"); db.commit()
    except Exception as exc:
        db.rollback(); task=db.get(BackgroundTask,task_id)
        if transient_provider_error(exc) and self.request.retries < self.max_retries:
            if task:
                lesson=db.get(Lesson,lesson_id)
                if lesson:
                    setattr(lesson,kind+"_qc_status","queued")
                    db.commit()
                update_task(db,task,"queued",task.progress,"Temporary Groq error; retrying")
            raise self.retry(exc=exc,countdown=max(1, int(getattr(exc, "retry_after", 10) or 10)))
        if task:
            lesson=db.get(Lesson,lesson_id)
            if lesson:
                setattr(lesson,kind+"_qc_status","failed")
                db.commit()
            update_task(db,task,"failed",task.progress,"Quality control failed",str(exc))
        if lesson:
            setattr(lesson,kind+"_qc_status","failed"); db.commit()
    finally: db.close()
