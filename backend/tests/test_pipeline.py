from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from test_api import create_account,auth
from app import main
from app.database import Base,engine
from app.tasks import pipeline
from app.database import SessionLocal
from app.models import BackgroundTask,ResearchSource,QCReport,Lesson

@pytest.fixture
def client():
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client

SAMPLES=[
    ("HTTP Requests and Responses","Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."),
    ("Introduction to Machine Learning","Explain supervised and unsupervised learning, distinguish between classification and regression, and identify practical applications of both learning approaches.")
]

def test_full_mocked_assignment_workflows(client,monkeypatch):
    sources=[
        {"type":"Website","title":"Official technical reference","url":"https://docs.example/reference","description":"Test-only mocked reference."},
        {"type":"Book","title":"Learning foundations","url":"https://books.example/item","authors":["Example Author"],"description":"Test-only mocked book metadata."},
        {"type":"YouTube","title":"Topic walkthrough","url":"https://youtube.example/video","channel":"Example Channel","description":"Test-only mocked video metadata."}
    ]
    factual={"score":91,"issue_count":1,"issues":[{"id":"F-1","section":"introduction","claim":"Example claim","description":"Evidence should be reviewed.","severity":"Medium","evidence":"Mock evidence","suggested_correction":"A source-aligned introduction.","confidence":0.8}]}
    instructional={"score":86,"alignment_score":90,"clarity_score":85,"structure_score":88,"practical_relevance_score":82,"assessment_quality_score":84,"time_assessment":"45 minutes total","issues":[{"id":"I-1","section":"introduction","weakness":"Could be clearer","explanation":"A brief improvement is suggested.","severity":"Low","suggested_improvement":"A clearer introduction.","expected_learning_benefit":"Improved comprehension."}]}
    monkeypatch.setattr(pipeline.ResearchService,"collect",lambda self,title,objective:{"all":sources,"web":sources[:1],"books":sources[1:2],"youtube":sources[2:],"errors":{}})
    monkeypatch.setattr(pipeline.FactualQCService,"audit",lambda self,lesson,sources:factual)
    monkeypatch.setattr(pipeline.InstructionalQCService,"audit",lambda self,lesson,objective,**kwargs:instructional)
    token=create_account(client,"pipeline@example.com"); headers=auth(token)
    for index,(title,objective) in enumerate(SAMPLES):
        generated={"title":title,"objective":objective,"audience":"Introductory learners","prerequisites":[],"duration_minutes":45,"outcomes":["Explain core concepts","Compare related approaches","Apply the ideas"],"introduction":"Evidence-backed opening.","modules":[{"title":"Core concepts","minutes":20,"explanation":"A concise test lesson.","example":"Example.","practical_application":"Practice."}],"demonstration":"A short demonstration.","activities":[{"title":"Practice","minutes":8,"instructions":"Apply the concept."}],"knowledge_checks":[{"type":"short answer","question":"What did you learn?","answer":"A clear explanation.","explanation":"Checks the objective."}],"summary":["Review the ideas."],"resources":[x["url"] for x in sources],"references":[{"title":x["title"],"url":x["url"],"type":x["type"],"supports":"Core content"} for x in sources],"time_plan":[{"section":"Introduction","minutes":5},{"section":"Concepts","minutes":20},{"section":"Demonstration","minutes":7},{"section":"Activity","minutes":8},{"section":"Knowledge check","minutes":3},{"section":"Summary","minutes":2}]}
        monkeypatch.setattr(pipeline.LessonGenerationService,"generate",lambda self,*_args,_lesson=generated:_lesson)
        lesson=client.post("/api/lessons",headers=headers,json={"title":title,"objective":objective,"audience":"Introductory learners","difficulty":"Beginner"}).json()
        with patch("app.api.routes.celery_app.send_task"):
            queued=client.post(f"/api/lessons/{lesson['id']}/generate",headers=headers).json()
        pipeline.generate_lesson_task.run(queued["task_id"],lesson["id"])
        task_result=client.get("/api/tasks/"+queued["task_id"],headers=headers).json()
        assert task_result["status"]=="completed",task_result
        final=client.get(f"/api/lessons/{lesson['id']}",headers=headers).json()
        assert final["lesson"]["duration_minutes"]==45
        assert sum(item["minutes"] for item in final["lesson"]["time_plan"])==45
        assert len(client.get(f"/api/lessons/{lesson['id']}/sources",headers=headers).json())==3
        reports=client.get(f"/api/lessons/{lesson['id']}/qc",headers=headers).json()
        assert reports["factual"]["score"]==91 and reports["instructional"]["score"]==86
        assert reports["factual"]["report"] is not reports["instructional"]["report"]
        edit=client.patch(f"/api/lessons/{lesson['id']}/sections",headers=headers,json={"sections":{"introduction":"Instructor-approved edit"},"note":"Instructor review"})
        assert edit.json()["lesson"]["introduction"]=="Instructor-approved edit"
        assert client.get(f"/api/lessons/{lesson['id']}/revisions",headers=headers).json()
        assert client.get(f"/api/lessons/{lesson['id']}/export/pdf",headers=headers).content[:4]==b"%PDF"
        assert client.get(f"/api/lessons/{lesson['id']}/export/docx",headers=headers).content[:2]==b"PK"


def _lesson_with_content(client, email):
    token=create_account(client,email)
    headers=auth(token)
    lesson=client.post("/api/lessons",headers=headers,
                       json={"title":"Testing lesson","objective":"Explain the test topic"}).json()
    with SessionLocal() as db:
        record=db.get(Lesson,lesson["id"])
        record.lesson={"introduction":"A saved introduction"}
        db.add(ResearchSource(lesson_id=record.id,kind="Website",
                               title="Test source",url="https://example.test/source",
                               description="Evidence"))
        db.commit()
    return lesson["id"]


def test_qc_execution_identity_and_independent_inputs(client,monkeypatch):
    lesson_id=_lesson_with_content(client,"qc-independent@example.com")
    calls={}
    factual={"score":90,"issues":[]}
    instructional={"score":80,"issues":[]}

    def factual_audit(self, lesson, sources):
        calls["factual"]=(lesson,sources)
        return factual

    def instructional_audit(self, lesson, objective, **kwargs):
        calls["instructional"]=(lesson,objective,kwargs)
        return instructional

    monkeypatch.setattr(pipeline.FactualQCService,"audit",factual_audit)
    monkeypatch.setattr(pipeline.InstructionalQCService,"audit",instructional_audit)
    with SessionLocal() as db:
        for kind in ("factual","instructional"):
            task=BackgroundTask(id=f"{kind}-task-000000000000000000000000000000",
                                owner_id=1,lesson_id=lesson_id,kind="qc_"+kind)
            db.add(task)
        db.commit()
    pipeline.qc_task.run("factual-task-000000000000000000000000000000",lesson_id,"factual")
    pipeline.qc_task.run("instructional-task-000000000000000000000000000000",lesson_id,"instructional")
    assert calls["factual"][1][0]["title"]=="Test source"
    assert calls["instructional"][1]=="Explain the test topic"
    assert "report" not in calls["factual"][0]
    assert "report" not in calls["instructional"][0]
    with SessionLocal() as db:
        reports=db.query(QCReport).filter_by(lesson_id=lesson_id).all()
        assert {report.kind for report in reports}=={"factual","instructional"}
        assert {report.execution_id for report in reports}=={
            "factual-task-000000000000000000000000000000",
            "instructional-task-000000000000000000000000000000",
        }


def test_qc_retry_upserts_same_execution_without_duplicate(client,monkeypatch):
    lesson_id=_lesson_with_content(client,"qc-idempotent@example.com")
    monkeypatch.setattr(pipeline.FactualQCService,"audit",lambda self,lesson,sources:{"score":88,"issues":[]})
    with SessionLocal() as db:
        db.add(BackgroundTask(id="same-task-000000000000000000000000000000",
                              owner_id=1,lesson_id=lesson_id,kind="qc_factual"))
        db.commit()
    pipeline.qc_task.run("same-task-000000000000000000000000000000",lesson_id,"factual")
    pipeline.qc_task.run("same-task-000000000000000000000000000000",lesson_id,"factual")
    with SessionLocal() as db:
        assert db.query(QCReport).filter_by(lesson_id=lesson_id,kind="factual").count()==1


def test_terminal_generation_failures_update_stage_and_preserve_sources(client,monkeypatch):
    lesson_id=_lesson_with_content(client,"generation-failure@example.com")
    with SessionLocal() as db:
        task=BackgroundTask(id="generation-failure-000000000000000000000000000",
                            owner_id=1,lesson_id=lesson_id,kind="generate")
        db.add(task); db.commit()
    monkeypatch.setattr(pipeline.ResearchService,"collect",
                        lambda self,title,objective:{"all":[],"errors":{"tavily":"unavailable"}})
    pipeline.generate_lesson_task.run("generation-failure-000000000000000000000000000",lesson_id)
    with SessionLocal() as db:
        lesson=db.get(Lesson,lesson_id)
        task=db.get(BackgroundTask,"generation-failure-000000000000000000000000000")
        assert lesson.research_status=="failed"
        assert task.status=="failed"

    lesson_id=_lesson_with_content(client,"generation-stage-failure@example.com")
    with SessionLocal() as db:
        task=BackgroundTask(id="generation-stage-failure-00000000000000000",
                            owner_id=1,lesson_id=lesson_id,kind="generate")
        db.add(task); db.commit()
    monkeypatch.setattr(pipeline.ResearchService,"collect",
                        lambda self,title,objective:{"all":[{"type":"Website","title":"Saved","url":"https://example.test"}],"errors":{}})
    monkeypatch.setattr(pipeline.LessonGenerationService,"generate",
                        lambda self,*args: (_ for _ in ()).throw(ValueError("invalid generation")))
    pipeline.generate_lesson_task.run("generation-stage-failure-00000000000000000",lesson_id)
    with SessionLocal() as db:
        lesson=db.get(Lesson,lesson_id)
        assert lesson.research_status=="completed"
        assert lesson.generation_status=="failed"
        assert db.query(ResearchSource).filter_by(lesson_id=lesson_id).count()>0
