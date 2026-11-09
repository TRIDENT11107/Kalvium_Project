from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from xml.etree import ElementTree

from pypdf import PdfReader

from modules.exporter import export_docx,export_pdf


def lesson():
    return {
        "title":"Export lesson",
        "objective":"Explain the topic",
        "introduction":"Readable introduction",
        "references":[{"title":"Official source","url":"https://example.test/docs","supports":"Core evidence"}],
    }


def test_pdf_contains_lesson_and_reference_link():
    output=export_pdf(lesson(),{"score":90},{"score":80})
    reader=PdfReader(BytesIO(output))
    text="\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Export lesson" in text
    assert "Official source" in text
    assert "Factual quality audit" in text
    annotations=[annotation.get_object() for page in reader.pages for annotation in (page.get("/Annots") or [])]
    assert any(annotation.get("/A",{}).get("/URI")=="https://example.test/docs" for annotation in annotations)


def test_docx_contains_editable_text_and_hyperlink():
    output=export_docx(lesson(),{"score":90},{"score":80})
    with ZipFile(BytesIO(output)) as archive:
        document=archive.read("word/document.xml")
        relationships=archive.read("word/_rels/document.xml.rels")
    root=ElementTree.fromstring(document)
    text=" ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    assert "Export lesson" in text and "Official source" in text
    assert b"https://example.test/docs" in relationships


def test_exports_are_generated_in_memory_without_files():
    with TemporaryDirectory() as directory:
        before=set(Path(directory).iterdir())
        pdf=export_pdf(lesson(),{}, {})
        docx=export_docx(lesson(),{}, {})
        assert pdf[:4]==b"%PDF"
        assert docx[:2]==b"PK"
        assert set(Path(directory).iterdir())==before
