import io
from xml.sax.saxutils import escape, quoteattr
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
from reportlab.lib.styles import getSampleStyleSheet

def flatten(value):
    if isinstance(value,dict): return "\n".join(str(k).replace("_"," ").title()+": "+flatten(v) for k,v in value.items())
    if isinstance(value,list): return "\n".join("- "+flatten(x) for x in value)
    return str(value)

def add_hyperlink(paragraph,text,url):
    if not url.startswith(("https://","http://")):
        paragraph.add_run(text); return
    relation=paragraph.part.relate_to(url,RT.HYPERLINK,is_external=True)
    link=OxmlElement("w:hyperlink"); link.set(qn("r:id"),relation)
    run=OxmlElement("w:r"); props=OxmlElement("w:rPr")
    color=OxmlElement("w:color"); color.set(qn("w:val"),"276C54"); props.append(color)
    underline=OxmlElement("w:u"); underline.set(qn("w:val"),"single"); props.append(underline)
    run.append(props); node=OxmlElement("w:t"); node.text=text; run.append(node); link.append(run); paragraph._p.append(link)

def add_docx_resources(document,key,value):
    if key in ("references","source_references") and isinstance(value,list):
        for item in value:
            if isinstance(item,dict):
                p=document.add_paragraph(style="List Bullet")
                add_hyperlink(p,str(item.get("title") or item.get("url") or "Reference"),str(item.get("url","")))
                if item.get("supports"): p.add_run(" - "+str(item["supports"]))
            else: document.add_paragraph(str(item),style="List Bullet")
        return True
    if key=="resources" and isinstance(value,list):
        for item in value:
            p=document.add_paragraph(style="List Bullet")
            url=item.get("url","") if isinstance(item,dict) else str(item)
            label=(item.get("title") or url) if isinstance(item,dict) else url
            add_hyperlink(p,str(label),url)
        return True
    return False

def add_pdf_resources(story,styles,key,value):
    if key in ("references","source_references") and isinstance(value,list):
        for item in value:
            if isinstance(item,dict):
                title=str(item.get("title") or item.get("url") or "Reference")
                url=str(item.get("url","")); label=escape(title)
                if url.startswith(("https://","http://")):
                    label="<link href="+quoteattr(url)+" color=\"#276C54\">"+label+"</link>"
                if item.get("supports"): label+=" - "+escape(str(item["supports"]))
                story.append(Paragraph("- "+label,styles["BodyText"]))
            else: story.append(Paragraph("- "+escape(str(item)),styles["BodyText"]))
        return True
    if key=="resources" and isinstance(value,list):
        for item in value:
            url=item.get("url","") if isinstance(item,dict) else str(item)
            label=(item.get("title") or url) if isinstance(item,dict) else url
            safe=escape(str(label))
            if url.startswith(("https://","http://")):
                safe="<link href="+quoteattr(url)+" color=\"#276C54\">"+safe+"</link>"
            story.append(Paragraph("- "+safe,styles["BodyText"]))
        return True
    return False

def export_docx(lesson,factual,instructional):
    d=Document(); d.add_heading(lesson.get("title","Lesson"),0)
    d.add_paragraph("Learning objective: "+lesson.get("objective",""))
    for key,value in lesson.items():
        if key not in ("title","objective"):
            d.add_heading(key.replace("_"," ").title(),1)
            if not add_docx_resources(d,key,value): d.add_paragraph(flatten(value))
    if factual:
        d.add_page_break(); d.add_heading("Factual quality audit",1); d.add_paragraph(flatten(factual))
    if instructional:
        d.add_page_break(); d.add_heading("Instructional quality audit",1); d.add_paragraph(flatten(instructional))
    out=io.BytesIO(); d.save(out); return out.getvalue()

def export_pdf(lesson,factual,instructional):
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=letter); styles=getSampleStyleSheet(); story=[]
    story.append(Paragraph(escape(lesson.get("title","Lesson")),styles["Title"]))
    for key,value in lesson.items():
        story.append(Paragraph(escape(key.replace("_"," ").title()),styles["Heading2"]))
        if not add_pdf_resources(story,styles,key,value):
            text=escape(flatten(value)).replace("\n","<br/>")
            story.append(Paragraph(text,styles["BodyText"]))
        story.append(Spacer(1,8))
    for heading,data in [("Factual quality audit",factual),("Instructional quality audit",instructional)]:
        if not data: continue
        story.append(PageBreak())
        story.append(Paragraph(heading,styles["Heading1"]))
        story.append(Paragraph(escape(flatten(data)).replace("\n","<br/>"),styles["BodyText"]))
    doc.build(story); return out.getvalue()
