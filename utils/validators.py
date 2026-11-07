def validate_inputs(title, objective):
    title=(title or "").strip(); objective=(objective or "").strip()
    if not title: raise ValueError("Enter a lesson title.")
    if not objective: raise ValueError("Enter a learning objective.")
    if len(title)>180 or len(objective)>2000: raise ValueError("Title or objective exceeds the supported length.")
    return title,objective
