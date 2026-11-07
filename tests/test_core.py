import json, tempfile, unittest
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch, Mock
from database import db
from modules.lesson_generator import generate_lesson
from modules.factual_qc import run_factual_qc, calculate_factual_score, normalize_factual_report
from modules.instructional_qc import run_instructional_qc
from modules.research_engine import books_search, youtube_search, web_search
from modules.exporter import export_pdf, export_docx
from utils.validators import validate_inputs

class ValidatorsTests(unittest.TestCase):
    def test_empty_inputs(self):
        with self.assertRaises(ValueError): validate_inputs("","objective")
        with self.assertRaises(ValueError): validate_inputs("title"," ")

class GenerationTests(unittest.TestCase):
    def test_blocks_empty_sources(self):
        with self.assertRaises(ValueError): generate_lesson("title","objective",[])
    @patch("modules.lesson_generator.generate_json")
    def test_duration_and_structure(self,mock):
        mock.return_value={"time_plan":[{"section":"A","minutes":45}],"outcomes":["Do"],"modules":[{"title":"Topic"}]}
        self.assertEqual(generate_lesson("T","O",[{"url":"https://example.org"}])["duration_minutes"],45)
    @patch("modules.lesson_generator.generate_json")
    def test_bad_duration_rejected(self,mock):
        mock.return_value={"time_plan":[{"section":"A","minutes":40}],"outcomes":["Do"],"modules":[{"title":"Topic"}]}
        with self.assertRaises(ValueError): generate_lesson("T","O",[{"url":"x"}])
    @patch("modules.lesson_generator.generate_json")
    def test_invalid_time_plan_is_corrected_with_a_focused_call(self,mock):
        mock.side_effect=[
            {"time_plan":[{"section":"A","minutes":40}],"outcomes":["Do"],"modules":[{"title":"Topic"}]},
            {"time_plan":[{"section":"A","minutes":45}]},
        ]
        lesson=generate_lesson("T","O",[{"url":"https://example.org"}])
        self.assertEqual(lesson["duration_minutes"],45)
        self.assertEqual(mock.call_count,2)

class ResearchTests(unittest.TestCase):
    @patch("modules.research_engine.requests.get")
    def test_books_metadata(self,mock):
        response=Mock(); response.json.return_value={"items":[{"volumeInfo":{"title":"Book","authors":["A"],"infoLink":"https://books.example"}}]}; response.raise_for_status.return_value=None; mock.return_value=response
        items,error=books_search("topic"); self.assertIsNone(error); self.assertEqual(items[0]["authors"],["A"])
    @patch("modules.research_engine.YOUTUBE_API_KEY","key")
    @patch("modules.research_engine.requests.get")
    def test_youtube_id_url(self,mock):
        response=Mock(); response.json.return_value={"items":[{"id":{"videoId":"abc"},"snippet":{"title":"Video"}}]}; response.raise_for_status.return_value=None; mock.return_value=response
        items,_=youtube_search("topic"); self.assertEqual(items[0]["url"],"https://www.youtube.com/watch?v=abc")
    @patch("modules.research_engine.TAVILY_API_KEY","")
    def test_missing_tavily_key(self):
        self.assertIn("not configured",web_search("query")[1])

class QCTests(unittest.TestCase):
    def test_factual_score_penalizes_false_more_than_unsupported(self):
        criteria={"claim_accuracy":100,"evidence_completeness":100,"source_reliability":100,"consistency":100}
        unsupported,_=calculate_factual_score(criteria,[{"classification":"unsupported"}])
        false,_=calculate_factual_score(criteria,[{"classification":"false"}])
        self.assertLess(false,unsupported)

    def test_factual_score_handles_missing_evidence(self):
        report=normalize_factual_report({"evidence_available":False,"score_breakdown":{"claim_accuracy":90,"evidence_completeness":90,"source_reliability":90,"consistency":90},"issues":[]})
        self.assertLess(report["score"],90)
        self.assertLessEqual(report["score_breakdown"]["evidence_completeness"],20)

    def test_malformed_factual_response_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_factual_report({"score_breakdown":[]})

    @patch("modules.factual_qc.generate_json",return_value={"score_breakdown":{"claim_accuracy":50,"evidence_completeness":50,"source_reliability":50,"consistency":50},"issues":[]})
    def test_factual_independent_call(self,mock):
        report=run_factual_qc({},[])
        self.assertEqual(report["score"],50)
        self.assertEqual(report["score_breakdown"]["evidence_completeness"],50)
        self.assertEqual(report["issue_count"],0)
        mock.assert_called_once()
    @patch("modules.instructional_qc.generate_json",return_value={"score":80})
    def test_instructional_independent_call(self,mock):
        self.assertEqual(run_instructional_qc({}),{"score":80}); mock.assert_called_once()

class DatabaseExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        patcher=patch("database.db.DATABASE_URL",self.temp.name+"/test.db"); patcher.start(); self.addCleanup(patcher.stop)
        db.init_db()
    def tearDown(self): self.temp.cleanup()
    def test_persistence_revision_delete(self):
        lesson={"title":"Test"}; lid=db.create_lesson("Test","Objective",lesson,[])
        db.update_lesson(lid,"Test","Objective",{"title":"Edited"})
        self.assertEqual(json.loads(db.get_lesson(lid)["lesson_json"])["title"],"Edited")
        self.assertEqual(len(db.get_revisions(lid)),2); db.delete_lesson(lid); self.assertIsNone(db.get_lesson(lid))
    def test_exports_are_documents(self):
        self.assertEqual(export_docx({"title":"T","objective":"O"},{},{})[:2],b"PK")
        self.assertEqual(export_pdf({"title":"T","objective":"O"},{},{})[:4],b"%PDF")
    def test_reference_links_are_clickable_in_both_exports(self):
        lesson={"title":"Links","objective":"O","references":[{"title":"Reference","url":"https://example.com/source"}]}
        doc=export_docx(lesson,{},{}); pdf=export_pdf(lesson,{},{})
        with ZipFile(BytesIO(doc)) as package:
            relationships=package.read("word/_rels/document.xml.rels")
            self.assertIn(b"https://example.com/source",relationships)
        self.assertIn(b"https://example.com/source",pdf)
        self.assertIn(b"/Annots",pdf)

if __name__=="__main__": unittest.main()
