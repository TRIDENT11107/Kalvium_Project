from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
import json
from app.database import get_db
from app.models import User,Lesson,ResearchSource,QCReport,LessonRevision,BackgroundTask,Recommendation,LessonSection,QCIssue
from app.security import current_user
from app.schemas.api import LessonCreate,LessonPatch,SectionsPatch,ResearchRequest,RecommendationApply,RevisionCreate
from app.celery_app import celery_app
from app.services.research import ResearchService
from app.services.lesson_management import LessonManagementService
from app.services.export_service import ExportService
from utils.lesson_validation import validate_lesson_duration
import uuid
router=APIRouter(prefix="/api",tags=["lessons"])
def owned_lesson(lesson_id:int,db:Session,user:User):
    return LessonManagementService().get_owned(db,lesson_id,user.id)
def revision_snapshot(lesson,note,**overrides):
    values={"lesson":dict(lesson.lesson or {}),"title":lesson.title,"objective":lesson.objective,"audience":lesson.audience,"difficulty":lesson.difficulty,"status":lesson.status}
    values.update(overrides)
    return LessonRevision(lesson_id=lesson.id,note=note,**values)
def add_revision_if_changed(db,lesson,note):
    latest=db.query(LessonRevision).filter_by(lesson_id=lesson.id).order_by(desc(LessonRevision.id)).first()
    current={"lesson":lesson.lesson or {},"title":lesson.title,"objective":lesson.objective,
             "audience":lesson.audience,"difficulty":lesson.difficulty,"status":lesson.status}
    if latest and all(current[key]==getattr(latest,key) for key in current):
        return False
    db.add(revision_snapshot(lesson,note))
    return True
def lesson_out(x):
    return {"id":x.id,"title":x.title,"objective":x.objective,"audience":x.audience,"difficulty":x.difficulty,"status":x.status,"lesson":x.lesson or {},"research_status":x.research_status,"generation_status":x.generation_status,"factual_qc_status":x.factual_qc_status,"instructional_qc_status":x.instructional_qc_status,"created_at":x.created_at,"updated_at":x.updated_at}
def latest_reports(db,lesson_id):
    reports=db.query(QCReport).filter_by(lesson_id=lesson_id).order_by(
        desc(QCReport.created_at), desc(QCReport.id)
    ).all()
    latest={}
    for report in reports:
        latest.setdefault(report.kind,report)
    return latest
def lesson_export_data(lesson):
    data=dict(lesson.lesson or {})
    references=list(data.get("references") or [])
    references.extend({
        "title":source.title,"url":source.url,"type":source.kind,
        "provider":(source.metadata_json or {}).get("provider")
    } for source in lesson.sources)
    seen=set()
    data["references"]=[item for item in references if not (
        (key := (item.get("url") if isinstance(item,dict) else str(item))) in seen or seen.add(key)
    )]
    return data
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
    lessons=db.query(Lesson).filter_by(owner_id=user.id).order_by(desc(Lesson.updated_at)).all()
    return {"total":len(lessons),"drafts":sum(x.status=="draft" for x in lessons),"in_review":sum(x.status=="review" for x in lessons),"completed":sum(x.status=="completed" for x in lessons),"recent":[lesson_out(x) for x in lessons[:6]]}
@router.post("/lessons",status_code=201)
def create_lesson(body:LessonCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=Lesson(owner_id=user.id,title=body.title.strip(),objective=body.objective.strip(),audience=body.audience,difficulty=body.difficulty,status="draft",lesson={})
    db.add(lesson); db.commit(); db.refresh(lesson)
    db.add(LessonRevision(lesson_id=lesson.id,lesson={},title=lesson.title,objective=lesson.objective,audience=lesson.audience,difficulty=lesson.difficulty,status=lesson.status,note="Lesson created")); db.commit()
    return lesson_out(lesson)
@router.get("/lessons")
def list_lessons(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return [lesson_out(x) for x in db.query(Lesson).filter_by(owner_id=user.id).order_by(desc(Lesson.updated_at)).all()]
@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return lesson_out(owned_lesson(lesson_id,db,user))
def persist_sections(db,lesson):
    db.query(LessonSection).filter_by(lesson_id=lesson.id).delete()
    excluded={"duration_minutes","time_plan"}
    for index,(key,value) in enumerate((lesson.lesson or {}).items()):
        if key in excluded: continue
        db.add(LessonSection(lesson_id=lesson.id,section_key=key,title=key.replace("_"," ").title(),content=value,order_index=index))

@router.patch("/lessons/{lesson_id}")
def patch_lesson(lesson_id:int,body:LessonPatch,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); changes=body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ("draft","review","completed"):
        raise HTTPException(422,"Invalid lesson status")
    if "lesson" in changes and changes["lesson"] is not None:
        merged=dict(lesson.lesson or {})
        for section,value in changes["lesson"].items():
            if value is None: merged.pop(section,None)
            else: merged[section]=value
        changes["lesson"]=merged
        if "time_plan" in merged or "duration_minutes" in merged:
            try:
                validate_lesson_duration(merged)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        add_revision_if_changed(db,lesson,"Before manual edit")
    for key,value in changes.items(): setattr(lesson,key,value)
    if "lesson" in changes: persist_sections(db,lesson)
    db.commit(); db.refresh(lesson); return lesson_out(lesson)
@router.delete("/lessons/{lesson_id}",status_code=204)
def remove_lesson(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); db.delete(lesson); db.commit(); return Response(status_code=204)
@router.post("/research")
def research(body:ResearchRequest,user:User=Depends(current_user)):
    result=ResearchService().collect(body.title,body.objective)
    if not result["all"]: raise HTTPException(503,{"message":"No research sources were available; configure providers and retry.","providers":result["errors"]})
    return result
@router.get("/lessons/{lesson_id}/sources")
def get_sources(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    return [dict(id=s.id,type=s.kind,title=s.title,url=s.url,description=s.description,**(s.metadata_json or {})) for s in lesson.sources]
@router.post("/lessons/{lesson_id}/generate",status_code=202)
def generate(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); tid=str(uuid.uuid4())
    task=BackgroundTask(id=tid,owner_id=user.id,lesson_id=lesson.id,kind="generate",status="queued",progress=0,message="Queued")
    lesson.research_status="queued"; lesson.generation_status="queued"
    db.add(task); db.commit()
    try:
        celery_app.send_task("app.tasks.pipeline.generate_lesson_task",args=[tid,lesson.id])
    except Exception as exc:
        task.status="failed"; task.message="Unable to publish generation task"; task.error=str(exc)
        lesson.research_status="failed"; lesson.generation_status="failed"; db.commit()
        raise HTTPException(503,"Unable to publish generation task")
    return {"task_id":tid,"status":"queued"}
@router.get("/tasks/{task_id}")
def task_status(task_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    task=db.get(BackgroundTask,task_id)
    if not task or task.owner_id!=user.id: raise HTTPException(404,"Task not found")
    return {"task_id":task.id,"status":task.status,"progress":task.progress,"message":task.message,"error":task.error}
@router.post("/lessons/{lesson_id}/qc/factual",status_code=202)
def qc_factual(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return queue_qc(lesson_id,"factual",db,user)
@router.post("/lessons/{lesson_id}/qc/instructional",status_code=202)
def qc_instructional(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return queue_qc(lesson_id,"instructional",db,user)
def queue_qc(lesson_id,kind,db,user):
    lesson=owned_lesson(lesson_id,db,user); tid=str(uuid.uuid4())
    task=BackgroundTask(id=tid,owner_id=user.id,lesson_id=lesson.id,kind="qc_"+kind,status="queued",progress=0,message="Queued")
    setattr(lesson,kind+"_qc_status","queued")
    db.add(task); db.commit()
    try:
        celery_app.send_task("app.tasks.pipeline.qc_task",args=[tid,lesson.id,kind])
    except Exception as exc:
        task.status="failed"; task.message="Unable to publish QC task"; task.error=str(exc)
        setattr(lesson,kind+"_qc_status","failed"); db.commit()
        raise HTTPException(503,"Unable to publish QC task")
    return {"task_id":tid,"status":"queued"}
@router.get("/lessons/{lesson_id}/qc")
def get_qc(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    reports=db.query(QCReport).filter_by(lesson_id=lesson.id).order_by(desc(QCReport.created_at),desc(QCReport.id)).all()
    result={}
    for report in reports:
        if report.kind in result: continue
        payload=dict(report.report or {})
        statuses={x.issue_key:x.status for x in db.query(QCIssue).filter_by(report_id=report.id).all()}
        statuses.update({x.issue_key:x.status for x in db.query(Recommendation).filter_by(lesson_id=lesson.id).all()})
        for issue in payload.get("issues",[]):
            issue["status"]=statuses.get(report.kind+":"+str(issue.get("id")),"open")
        result[report.kind]={"id":report.id,"score":report.score,"report":payload,"created_at":report.created_at}
    return result
@router.patch("/lessons/{lesson_id}/sections")
def patch_sections(lesson_id:int,body:SectionsPatch,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    updated=dict(lesson.lesson or {})
    for section,value in body.sections.items():
        if value is None: updated.pop(section,None)
        else: updated[section]=value
    try:
        if "time_plan" in updated or "duration_minutes" in updated:
            validate_lesson_duration(updated)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    old_state={"lesson":lesson.lesson or {},"title":lesson.title,"objective":lesson.objective,
               "audience":lesson.audience,"difficulty":lesson.difficulty,"status":lesson.status}
    new_state={"lesson":updated,"title":body.title if body.title is not None else lesson.title,
               "objective":body.objective if body.objective is not None else lesson.objective,
               "audience":body.audience if body.audience is not None else lesson.audience,
               "difficulty":body.difficulty if body.difficulty is not None else lesson.difficulty,
               "status":lesson.status}
    if old_state==new_state:
        return lesson_out(lesson)
    add_revision_if_changed(db,lesson,body.note)
    lesson.lesson=updated
    for key in ("title","objective","audience","difficulty"):
        value=getattr(body,key)
        if value is not None: setattr(lesson,key,value)
    persist_sections(db,lesson);     db.commit(); db.refresh(lesson); return lesson_out(lesson)
@router.post("/lessons/{lesson_id}/revisions",status_code=201)
def create_revision(lesson_id:int,body:RevisionCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); revision=revision_snapshot(lesson,body.note)
    db.add(revision); db.commit(); db.refresh(revision)
    return {"id":revision.id,"lesson":revision.lesson,"title":revision.title,"objective":revision.objective,"note":revision.note,"created_at":revision.created_at}
@router.get("/lessons/{lesson_id}/revisions")
def revisions(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    return [{"id":r.id,"lesson":r.lesson,"title":r.title,"objective":r.objective,"audience":r.audience,"difficulty":r.difficulty,"status":r.status,"note":r.note,"created_at":r.created_at} for r in db.query(LessonRevision).filter_by(lesson_id=lesson.id).order_by(desc(LessonRevision.created_at)).all()]
@router.post("/lessons/{lesson_id}/revisions/{revision_id}/restore")
def restore_revision(lesson_id:int,revision_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    revision=db.query(LessonRevision).filter_by(id=revision_id,lesson_id=lesson.id).first()
    if not revision: raise HTTPException(404,"Revision not found")
    if revision.lesson==lesson.lesson and revision.title==lesson.title and revision.objective==lesson.objective:
        return lesson_out(lesson)
    add_revision_if_changed(db,lesson,"Before restoring revision "+str(revision_id))
    lesson.lesson=revision.lesson; lesson.title=revision.title or lesson.title; lesson.objective=revision.objective or lesson.objective
    lesson.audience=revision.audience; lesson.difficulty=revision.difficulty; lesson.status=revision.status or "review"
    persist_sections(db,lesson); db.commit(); db.refresh(lesson)
    return lesson_out(lesson)
@router.post("/lessons/{lesson_id}/recommendations/{recommendation_id}/apply")
def apply_recommendation(lesson_id:int,recommendation_id:str,body:RecommendationApply,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    try: kind,issue_id=recommendation_id.split(":",1)
    except ValueError: raise HTTPException(404,"Recommendation not found")
    if kind not in ("factual","instructional"): raise HTTPException(404,"Recommendation not found")
    candidate=None; source_report=None
    reports=db.query(QCReport).filter_by(lesson_id=lesson.id,kind=kind).order_by(desc(QCReport.created_at),desc(QCReport.id)).all()
    for report in reports:
        for issue in report.report.get("issues",[]):
            if str(issue.get("id"))==issue_id: candidate=issue; source_report=report; break
        if candidate: break
    if not candidate: raise HTTPException(404,"Recommendation not found")
    rec=db.query(Recommendation).filter_by(lesson_id=lesson.id,issue_key=recommendation_id).first()
    if rec and rec.status=="applied":
        raise HTTPException(409,"Recommendation has already been applied.")
    if rec and rec.status=="rejected":
        raise HTTPException(409,"Recommendation was rejected and cannot be applied.")
    issue=candidate; section=str(issue.get("section", "")); normalized=section.lower().replace(" ","_").replace("-","_")
    field=next((key for key in lesson.lesson if key.lower()==normalized),None)
    if not field: raise HTTPException(422,"This recommendation is not mapped to a lesson field; edit the section manually.")
    value=body.replacement if body.replacement is not None else issue.get("suggested_correction") or issue.get("suggested_improvement")
    if value is None: raise HTTPException(422,"Recommendation has no suggested change")
    current_value=(lesson.lesson or {}).get(field)
    suggested_value=issue.get("suggested_correction") or issue.get("suggested_improvement")
    if isinstance(value,str) and (isinstance(current_value,(dict,list)) or isinstance(suggested_value,(dict,list))):
        try:
            value=json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(422,"Structured recommendations must be valid JSON.") from exc
    updated=dict(lesson.lesson); updated[field]=value
    if "time_plan" in updated or "duration_minutes" in updated:
        try:
            validate_lesson_duration(updated)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(422,str(exc)) from exc
    add_revision_if_changed(db,lesson,"Before applying recommendation "+recommendation_id)
    lesson.lesson=updated
    if not rec: rec=Recommendation(lesson_id=lesson.id,issue_key=recommendation_id)
    rec.status="applied"; db.add(rec)
    qci=db.query(QCIssue).filter_by(report_id=source_report.id,issue_key=recommendation_id).first()
    if qci: qci.status="applied"
    db.commit()
    return {"applied":True,"section":field,"qc_layer":kind,"lesson":lesson_out(lesson)}
@router.post("/lessons/{lesson_id}/recommendations/{recommendation_id}/reject")
def reject_recommendation(lesson_id:int,recommendation_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    available={r.kind+":"+str(i.get("id")) for r in lesson.reports for i in r.report.get("issues",[])}
    if recommendation_id not in available: raise HTTPException(404,"Recommendation not found")
    rec=db.query(Recommendation).filter_by(lesson_id=lesson.id,issue_key=recommendation_id).first()
    if not rec: rec=Recommendation(lesson_id=lesson.id,issue_key=recommendation_id)
    rec.status="rejected"; db.add(rec)
    for report in lesson.reports:
        qci=db.query(QCIssue).filter_by(report_id=report.id,issue_key=recommendation_id).first()
        if qci: qci.status="rejected"
    db.commit()
    return {"rejected":True,"recommendation_id":recommendation_id}
@router.get("/lessons/{lesson_id}/recommendations")
def list_recommendations(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user)
    statuses={r.issue_key:r.status for r in db.query(Recommendation).filter_by(lesson_id=lesson.id).all()}
    return [{"id":report.kind+":"+str(i.get("id")),"type":report.kind,
             "status":statuses.get(report.kind+":"+str(i.get("id")),"open"),"issue":i}
            for report in latest_reports(db,lesson.id).values() for i in report.report.get("issues",[])]
@router.get("/lessons/{lesson_id}/export/pdf")
def pdf(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); reports={kind:report.report for kind,report in latest_reports(db,lesson.id).items()}
    lesson_data=lesson_export_data(lesson)
    return Response(ExportService.pdf(lesson,reports,lesson_data),media_type="application/pdf",headers={"Content-Disposition":'attachment; filename="lesson.pdf"'})
@router.get("/lessons/{lesson_id}/export/docx")
def docx(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); reports={kind:report.report for kind,report in latest_reports(db,lesson.id).items()}
    lesson_data=lesson_export_data(lesson)
    return Response(ExportService.docx(lesson,reports,lesson_data),media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",headers={"Content-Disposition":'attachment; filename="lesson.docx"'})
@router.get("/lessons/{lesson_id}/export/qc")
def export_qc(lesson_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lesson=owned_lesson(lesson_id,db,user); reports={kind:report.report for kind,report in latest_reports(db,lesson.id).items()}
    if not reports:
        raise HTTPException(409,"No successful QC reports are available. Run a QC stage and retry.")
    return Response(ExportService.qc_pdf(lesson,reports),media_type="application/pdf",headers={"Content-Disposition":'attachment; filename="quality-reports.pdf"'})
@router.get("/lessons/{lesson_id}/export/qc/{kind}")
def export_qc_kind(lesson_id:int,kind:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if kind not in ("factual","instructional"):
        raise HTTPException(404,"Unknown QC report type")
    lesson=owned_lesson(lesson_id,db,user)
    report=db.query(QCReport).filter_by(lesson_id=lesson.id,kind=kind).order_by(desc(QCReport.created_at)).first()
    if not report:
        raise HTTPException(409,kind.title()+" QC report is not available. Run this QC stage and retry.")
    return Response(ExportService.qc_pdf(lesson,{kind:report.report}),media_type="application/pdf",
                    headers={"Content-Disposition":f'attachment; filename="{kind}-quality-report.pdf"'})
