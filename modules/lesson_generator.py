from utils.llm_client import generate_json
from utils.validators import validate_inputs
from utils.lesson_validation import validate_lesson_duration
from utils.prompt_compaction import compact_json

def generate_lesson(title, objective, sources):
    title,objective=validate_inputs(title,objective)
    if not sources: raise ValueError("No research sources were retrieved. Configure research APIs and retry; generation is blocked to avoid unsupported content.")
    system="You are an evidence-grounded instructional designer. Use only supplied research for factual claims, cite source URLs in references, never invent citations. Return valid JSON matching requested keys. Design the lesson for exactly 45 minutes."
    source_context = [{
        "type": source.get("type"),
        "title": source.get("title"),
        "url": source.get("url"),
        "description": (source.get("description") or "")[:350],
        "authors": (source.get("authors") or [])[:3],
        "published": source.get("published"),
        "doi": source.get("doi"),
        "publisher": source.get("publisher"),
        "journal": source.get("journal"),
    } for source in sources]
    prompt="""Create a complete 45-minute lesson as JSON with keys: title, objective, audience, prerequisites (array), duration_minutes (45), outcomes (3-5 measurable strings), introduction (text), modules (array of objects with title, minutes, explanation, example, practical_application), demonstration (text), activities (array of objects with title, minutes, instructions), knowledge_checks (array of objects with type, question, choices, answer, explanation), summary (array), resources (array of source URLs actually supplied), references (array of objects title,url,type,supports), time_plan (array objects section,minutes). Include sufficient educational substance; avoid unsupported factual assertions. Time plan must total 45 minutes. Objective: """+objective+"\nLesson title: "+title+"\nSources: "+compact_json(source_context,string_limit=350,item_limit=24,key_limit=12)
    data=generate_json(system,prompt)
    data["title"]=title; data["objective"]=objective
    plan=data.get("time_plan",[])
    try:
        total_minutes=sum(int(item.get("minutes",0)) for item in plan)
    except (AttributeError, TypeError, ValueError):
        total_minutes=0
    if not plan or total_minutes!=45:
        repair_system="You are a lesson scheduler. Return one valid JSON object and nothing else."
        repair_context={
            "lesson_title": title,
            "objective": objective,
            "modules": [{"title":x.get("title"),"minutes":x.get("minutes")} for x in data.get("modules",[]) if isinstance(x,dict)],
            "activities": [{"title":x.get("title"),"minutes":x.get("minutes")} for x in data.get("activities",[]) if isinstance(x,dict)],
            "current_time_plan": plan,
        }
        repair_prompt=(
            "Return only {\"time_plan\":[{\"section\":string,\"minutes\":positive integer}]}. "
            "Create an accurate schedule for this 45-minute lesson. The minutes must sum "
            "to exactly 45. Preserve the lesson section order and use these details: "
            + compact_json(repair_context,string_limit=180,item_limit=8)
        )
        repaired=generate_json(repair_system,repair_prompt,max_completion_tokens=400)
        plan=repaired.get("time_plan",[])
        try:
            total_minutes=sum(int(item.get("minutes",0)) for item in plan)
        except (AttributeError, TypeError, ValueError):
            total_minutes=0
        if not plan or total_minutes!=45:
            raise ValueError("Generated lesson time plan did not validate to exactly 45 minutes after correction.")
    data["duration_minutes"]=sum(int(x["minutes"]) for x in plan)
    data["time_plan"]=plan
    validate_lesson_duration(data)
    if not data.get("outcomes") or not data.get("modules"): raise ValueError("Generated lesson is missing required outcomes or content modules.")
    return data
