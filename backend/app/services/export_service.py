from app.services.exports import build_pdf, build_docx, build_qc_pdf

class ExportService:
    pdf=staticmethod(build_pdf)
    docx=staticmethod(build_docx)
    qc_pdf=staticmethod(build_qc_pdf)
