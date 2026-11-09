from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Any, Literal
class Credentials(BaseModel):
    full_name: str = Field(default="", max_length=160)
    email: EmailStr
    password: str=Field(min_length=8,max_length=128)
class ResetRequest(BaseModel):
    email: EmailStr
class ResetConfirm(BaseModel):
    token: str
    password: str=Field(min_length=8,max_length=128)
class UserOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int
    full_name:str
    email:str
class TokenOut(BaseModel):
    access_token:str
    token_type:str="bearer"
    user:UserOut
class LessonCreate(BaseModel):
    title:str=Field(min_length=1,max_length=180)
    objective:str=Field(min_length=1,max_length=2000)
    audience:str=""
    difficulty:Literal["Beginner","Intermediate","Advanced"]="Beginner"
    @field_validator("title","objective")
    @classmethod
    def require_text(cls,value:str)->str:
        value=value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value
class LessonPatch(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=180)
    objective:str|None=Field(default=None,min_length=1,max_length=2000)
    audience:str|None=None
    difficulty:str|None=None
    lesson:dict[str,Any]|None=None
    status:Literal["draft","review","completed"]|None=None
    @field_validator("title","objective")
    @classmethod
    def require_patch_text(cls,value:str|None)->str|None:
        if value is None:
            return value
        value=value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value
class SectionsPatch(BaseModel):
    sections:dict[str,Any]
    note:str="Instructor edit"
    title:str|None=None
    objective:str|None=None
    audience:str|None=None
    difficulty:str|None=None
    @field_validator("title","objective")
    @classmethod
    def require_section_text(cls,value:str|None)->str|None:
        if value is None:
            return value
        value=value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value
class LessonOut(BaseModel):
    id:int; title:str; objective:str; audience:str; difficulty:str; status:str; lesson:dict[str,Any]; created_at:Any; updated_at:Any
class ResearchRequest(BaseModel):
    title:str=Field(min_length=1,max_length=180)
    objective:str=Field(min_length=1,max_length=2000)
    @field_validator("title","objective")
    @classmethod
    def require_research_text(cls,value:str)->str:
        value=value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value
class RecommendationApply(BaseModel):
    replacement:Any|None=None
class RevisionCreate(BaseModel):
    note:str=Field(default="Instructor revision",max_length=300)
