import os, sys, tempfile
from io import BytesIO
from pathlib import Path
TEMP_DB=tempfile.NamedTemporaryFile(suffix=".db",delete=False)
TEMP_DB.close()
os.environ["DATABASE_URL"]="sqlite:///"+TEMP_DB.name.replace("\\","/")
os.environ["JWT_SECRET"]="unit-test-secret-with-enough-entropy-123456"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base,engine
from app.models import QCReport, QCIssue, LessonRevision, User
from app.database import SessionLocal
from unittest.mock import patch
import pytest
from pypdf import PdfReader

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c: yield c
    engine.dispose()
    try: os.unlink(TEMP_DB.name)
    except PermissionError: pass

def create_account(client,email="teacher@example.com"):
    response=client.post("/api/auth/register",json={"email":email,"password":"test-password-123"})
    assert response.status_code==201
    return response.json()["access_token"]

def auth(token): return {"Authorization":"Bearer "+token}

def test_health_and_auth(client):
    assert client.get("/health").json()=={"status":"ok"}
    token=create_account(client)
    assert client.get("/api/auth/me",headers=auth(token)).json()["email"]=="teacher@example.com"
    assert client.post("/api/auth/login",json={"email":"teacher@example.com","password":"wrong-pass"}).status_code==401
    assert client.post("/api/auth/register",json={"email":"teacher@example.com","password":"test-password-123"}).status_code==409

def test_lessons_edits_history_and_exports(client):
    token=create_account(client,"editor@example.com")
    headers=auth(token)
    created=client.post("/api/lessons",headers=headers,json={"title":"HTTP requests","objective":"Explain methods and status classes","difficulty":"Beginner"})
    assert created.status_code==201
    lid=created.json()["id"]
    patched=client.patch(f"/api/lessons/{lid}",headers=headers,json={"lesson":{"introduction":"Instructor edited this."}})
    assert patched.status_code==200
    assert patched.json()["lesson"]["introduction"]=="Instructor edited this."
    assert client.get(f"/api/lessons/{lid}/revisions",headers=headers).json()
    assert client.post(f"/api/lessons/{lid}/revisions",headers=headers,json={"note":"Named snapshot"}).status_code==201
    pdf=client.get(f"/api/lessons/{lid}/export/pdf",headers=headers)
    docx=client.get(f"/api/lessons/{lid}/export/docx",headers=headers)
    assert pdf.status_code==200 and pdf.content[:4]==b"%PDF"
    assert docx.status_code==200 and docx.content[:2]==b"PK"
    assert client.delete(f"/api/lessons/{lid}",headers=headers).status_code==204

def test_access_is_scoped_and_async_task_is_queued(client):
    token=create_account(client,"owner@example.com"); other=create_account(client,"other@example.com")
    headers=auth(token); theirs=auth(other)
    lesson=client.post("/api/lessons",headers=headers,json={"title":"Private","objective":"A private objective"}).json()
    assert client.get(f"/api/lessons/{lesson['id']}",headers=theirs).status_code==404
    with patch("app.api.routes.celery_app.send_task") as send:
        queued=client.post(f"/api/lessons/{lesson['id']}/generate",headers=headers)
        assert queued.status_code==202
        send.assert_called_once()
        status=client.get("/api/tasks/"+queued.json()["task_id"],headers=headers)
        assert status.json()["status"]=="queued"

def test_qc_recommendation_application_is_revisioned(client):
    token=create_account(client,"qc@example.com"); headers=auth(token)
    lesson=client.post("/api/lessons",headers=headers,json={"title":"QC","objective":"Test objective"}).json()
    lid=lesson["id"]
    client.patch(f"/api/lessons/{lid}",headers=headers,json={"lesson":{"introduction":"Initial introduction"}})
    with SessionLocal() as db:
        report=QCReport(lesson_id=lid,kind="factual",score=80,report={"issues":[{"id":"F-1","section":"introduction","suggested_correction":"Corrected introduction"}]});db.add(report);db.flush()
        db.add(QCIssue(report_id=report.id,issue_key="factual:F-1",section="introduction",severity="High",issue_data=report.report["issues"][0]));db.commit()
    response=client.post(f"/api/lessons/{lid}/recommendations/factual%3AF-1/apply",headers=headers,json={})
    assert response.status_code==200
    assert response.json()["lesson"]["lesson"]["introduction"]=="Corrected introduction"
    assert client.get(f"/api/lessons/{lid}/revisions",headers=headers).json()

def test_exports_select_latest_report_and_deduplicate_references(client):
    token=create_account(client,"latest-export@example.com"); headers=auth(token)
    lesson=client.post("/api/lessons",headers=headers,json={"title":"Export","objective":"Explain export"}).json()
    lid=lesson["id"]
    with SessionLocal() as db:
        db.add(QCReport(lesson_id=lid,kind="factual",score=40,
                        execution_id="00000000-0000-0000-0000-000000000001",
                        report={"score":40,"issues":[{"id":"old"}]}))
        db.add(QCReport(lesson_id=lid,kind="factual",score=95,
                        execution_id="00000000-0000-0000-0000-000000000002",
                        report={"score":95,"issues":[{"id":"new"}]}))
        db.commit()
    pdf=client.get(f"/api/lessons/{lid}/export/pdf",headers=headers)
    assert pdf.status_code==200
    text="\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "95" in text and "40" not in text

def test_research_requires_auth(client):
    response=client.post("/api/research",json={"title":"Topic","objective":"Understand topic"})
    assert response.status_code==401


def test_password_reset_token_is_one_time(client):
    from jose import jwt
    from app.settings import settings
    token=create_account(client,"reset@example.com")
    me=client.get("/api/auth/me",headers=auth(token)).json()
    with SessionLocal() as db:
        user=db.query(User).filter_by(id=me["id"]).one(); user.password_reset_jti="reset-test-jti"; db.commit()
    reset=jwt.encode({"sub":str(me["id"]),"jti":"reset-test-jti","purpose":"password_reset","exp":__import__("datetime").datetime.now(__import__("datetime").timezone.utc)+__import__("datetime").timedelta(minutes=10)},settings.jwt_secret,algorithm="HS256")
    response=client.post("/api/auth/password-reset/confirm",json={"token":reset,"password":"updated-password-456"})
    assert response.status_code==200
    assert client.post("/api/auth/password-reset/confirm",json={"token":reset,"password":"another-password-789"}).status_code==400
    assert client.post("/api/auth/login",json={"email":"reset@example.com","password":"updated-password-456"}).status_code==200
