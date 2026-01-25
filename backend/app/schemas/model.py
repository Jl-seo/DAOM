from pydantic import BaseModel
from typing import List, Optional

class FieldDefinition(BaseModel):
    key: str
    label: str
    description: Optional[str] = None  # 자연어 정의 (무엇을 추출할지)
    rules: Optional[str] = None  # 출력 보정/형태 정의 (자연어)
    type: str = "string"

class ComparisonSettings(BaseModel):
    """비교 설정 (comparison 모델 전용)"""
    confidence_threshold: float = 0.85  # 0.0-1.0 신뢰도 임계값
    ignore_position_changes: bool = True  # 위치 변경 무시
    ignore_color_changes: bool = False  # 색상 변경 무시
    ignore_font_changes: bool = True  # 폰트 변경 무시
    ignore_compression_noise: bool = True  # JPEG/이미지 압축 노이즈 무시 (기본 활성화)
    custom_ignore_rules: Optional[str] = None  # 추가 무시 규칙 (자연어)
    # 카테고리 커스터마이징
    allowed_categories: Optional[List[str]] = None  # 허용할 카테고리 목록 (설정 시 이것만 사용)
    excluded_categories: Optional[List[str]] = None  # 제외할 카테고리 목록
    custom_categories: Optional[List[dict]] = None  # 사용자 정의 카테고리 [{"key": "logo", "label": "로고", "description": "..."}]

class ExcelExportColumn(BaseModel):
    """엑셀 내보내기 열 정의"""
    key: str  # 내부 키 (e.g., "candidate", "description")
    label: str  # 헤더 표시명
    width: int = 15  # 열 너비
    enabled: bool = True  # 내보내기 포함 여부

class ExtractionModel(BaseModel):
    id: str
    name: str
    description: Optional[str] = None # 대체 내용 정의 등
    global_rules: Optional[str] = None # 전체적인 출력 형태/보정 정의
    data_structure: Optional[str] = "data" # 데이터 구조 타입: "table" (표), "data" (JSON 객체), "report" (문서)
    model_type: Optional[str] = "extraction" # "extraction" or "comparison"
    azure_model_id: Optional[str] = "prebuilt-layout" # Azure Document Intelligence Model ID (e.g. prebuilt-invoice)
    webhook_url: Optional[str] = None  # POST URL for automation after extraction confirmation
    allowedGroups: Optional[List[str]] = None # Access control groups
    fields: List[FieldDefinition]
    is_active: bool = True
    # Comparison-specific settings
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None

class ExtractionModelCreate(BaseModel):
    name: str
    description: Optional[str] = None
    global_rules: Optional[str] = None
    data_structure: Optional[str] = "data"
    model_type: Optional[str] = "extraction"
    webhook_url: Optional[str] = None  # POST URL for automation
    allowedGroups: Optional[List[str]] = None
    fields: List[FieldDefinition]
    # Comparison-specific settings
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None
