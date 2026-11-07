from modules.exporter import export_pdf,export_docx
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

def build_pdf(lesson,reports,data=None):
    return export_pdf({"title":lesson.title,"objective":lesson.objective,**(data or lesson.lesson or {})},reports.get("factual"),reports.get("instructional"))
def build_docx(lesson,reports,data=None):
    return export_docx({"title":lesson.title,"objective":lesson.objective,**(data or lesson.lesson or {})},reports.get("factual"),reports.get("instructional"))
def build_qc_pdf(lesson,reports):
    out=BytesIO(); styles=getSampleStyleSheet(); story=[Paragraph("Quality reports: "+lesson.title,styles["Title"])]
    for kind in ("factual","instructional"):
        story.append(Paragraph(kind.title()+" quality review",styles["Heading1"]))
        report=reports.get(kind,{})
        for key,value in report.items():
            text=(str(key)+": "+str(value)).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            story.append(Paragraph(text,styles["BodyText"])); story.append(Spacer(1,6))
    SimpleDocTemplate(out,pagesize=letter).build(story); return out.getvalue()
