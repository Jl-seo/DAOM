from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any


def default_beta_features() -> Dict[str, bool]:
    """Default beta features - all disabled by default."""
    return {
        "use_optimized_prompt": False,
        "use_vision_extraction": False,
        # DEPRECATED: ExcelMapper moved to _deprecated/
        # "use_virtual_excel_ocr": False
    }


class FieldDefinition(BaseModel):
    key: str
    label: str
    description: Optional[str] = None  # 자연어 정의 (무엇을 추출할지)
    rules: Optional[str] = None  # 출력 보정/형태 정의 (자연어)
    type: str = "string"
    is_dex_target: Optional[bool] = False # DEX 바코드 검증 타겟 여부

class ComparisonSettings(BaseModel):
    """비교 설정 (comparison 모델 전용)"""
    confidence_threshold: float = 0.85  # 0.0-1.0 신뢰도 임계값
    ignore_position_changes: bool = True  # 위치 변경 무시
    ignore_color_changes: bool = False  # 색상 변경 무시
    ignore_font_changes: bool = True  # 폰트 변경 무시
    ignore_compression_noise: bool = True  # JPEG/이미지 압축 노이즈 무시 (기본 활성화)
    custom_ignore_rules: Optional[str] = None  # 추가 무시 규칙 (자연어)
    output_language: str = "Korean"  # 출력 언어 (기본값: Korean)

    # Method Toggles (Component-Based Architecture)
    use_ssim_analysis: bool = True # 물리적 구조 분석 (Pixel/SSIM)
    use_vision_analysis: bool = False # 시각적 의미 분석 (Azure AI Vision) - 별도 설정 필요, 기본 비활성
    align_images: bool = True # 이미지 정렬 (Registration) 활성화 여부

    # 카테고리 커스터마이징
    allowed_categories: Optional[List[str]] = None  # 허용할 카테고리 목록 (설정 시 이것만 사용)
    excluded_categories: Optional[List[str]] = None  # 제외할 카테고리 목록
    custom_categories: Optional[List[dict]] = None  # 사용자 정의 카테고리 [{"key": "logo", "label": "로고", "description": "..."}]

    # SSIM Identity Gate
    ssim_identity_threshold: float = 0.95  # Global SSIM score gate (이 이상이면 LLM 호출 생략, 0.90~1.0)

class ExcelExportColumn(BaseModel):
    """엑셀 내보내기 열 정의"""
    key: str  # 내부 키 (e.g., \"candidate\", \"description\")
    label: str  # 헤더 표시명
    width: int = 15  # 열 너비
    enabled: bool = True  # 내보내기 포함 여부

class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore Cosmos system fields

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
    # Reference data for LLM context (Phase 1: structured JSON data)
    reference_data: Optional[Dict[str, Any]] = None  # 참고 데이터 (고객코드 매핑, 유효성 규칙 등)
    # Beta feature toggles - uses default_factory so missing DB values get defaults
    beta_features: Dict[str, bool] = Field(default_factory=default_beta_features)
    # Comparison-specific settings
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None

class ExtractionModelCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: Optional[str] = None
    global_rules: Optional[str] = None
    data_structure: Optional[str] = "data"
    model_type: Optional[str] = "extraction"
    webhook_url: Optional[str] = None  # POST URL for automation
    allowedGroups: Optional[List[str]] = None
    fields: List[FieldDefinition]
    # Reference data for LLM context (Phase 1: structured JSON data)
    reference_data: Optional[Dict[str, Any]] = None  # 참고 데이터 (고객코드 매핑, 유효성 규칙 등)
    # Beta feature toggles - uses default_factory so missing values get defaults
    beta_features: Dict[str, bool] = Field(default_factory=default_beta_features)
    # Comparison-specific settings
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None

