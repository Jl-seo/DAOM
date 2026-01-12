from pydantic import BaseModel
from typing import List, Optional

class FieldDefinition(BaseModel):
    key: str
    label: str
    description: Optional[str] = None  # 자연어 정의 (무엇을 추출할지)
    rules: Optional[str] = None  # 출력 보정/형태 정의 (자연어)
    type: str = "string"

class ExtractionModel(BaseModel):
    id: str
    name: str
    description: Optional[str] = None # 대체 내용 정의 등
    global_rules: Optional[str] = None # 전체적인 출력 형태/보정 정의
    data_structure: Optional[str] = "data" # 데이터 구조 타입: "table" (표), "data" (JSON 객체), "report" (문서)
    model_type: Optional[str] = "extraction" # "extraction" or "comparison"
    azure_model_id: Optional[str] = "prebuilt-layout" # Azure Document Intelligence Model ID (e.g. prebuilt-invoice)
    allowedGroups: Optional[List[str]] = None # Access control groups
    fields: List[FieldDefinition]
    is_active: bool = True

class ExtractionModelCreate(BaseModel):
    name: str
    description: Optional[str] = None
    global_rules: Optional[str] = None
    data_structure: Optional[str] = "data"
    model_type: Optional[str] = "extraction"
    allowedGroups: Optional[List[str]] = None
    fields: List[FieldDefinition]
