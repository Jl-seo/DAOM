from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Union


def default_beta_features() -> Dict[str, bool]:
    return {
        "use_optimized_prompt": False,
        "use_vision_extraction": False,
        "use_multi_table_analyzer": False  # New Feature: Direct JSON-level table mapping bypassing markdown conversion
    }

class PostProcessAction(str, Enum):
    SPLIT_CURRENCY = "split_currency"
    EXTRACT_DIGITS = "extract_digits"
    UPPERCASE = "uppercase"
    DATE_FORMAT_ISO = "date_format_iso"

class PostProcessRule(BaseModel):
    action: PostProcessAction
    target_field: str

class VibeDictionarySource(str, Enum):
    AI_GENERATED = "AI_GENERATED"
    MANUAL = "MANUAL"

class VibeDictionaryEntry(BaseModel):
    value: str  # The standard code (e.g. KRPUS)
    source: VibeDictionarySource = VibeDictionarySource.MANUAL
    is_verified: bool = True

class VibeDictionaryConfig(BaseModel):
    enabled: bool = False
    persona_prompt: str = ""
    target_fields: List[str] = []


class FieldDefinition(BaseModel):
    key: str
    label: str
    description: Optional[str] = None  # 자연어 정의 (무엇을 추출할지)
    rules: Optional[str] = None  # 출력 보정/형태 정의 (자연어)
    type: str = "string"
    is_dex_target: Optional[bool] = False # DEX 바코드 검증 타겟 여부
    dictionary: Optional[str] = None # Field-level dictionary mapping category (e.g., "port", "charge")
    required: bool = False # 필수 항목 추출 여부
    validation_regex: Optional[str] = None # 값 검증 정규식 (e.g., ^[A-Z0-9]+$)
    sub_fields: Optional[List[Dict[str, Any]]] = None # 하위 컬러 정의 (e.g. [{"key": "pol", "label": "POL", "dictionary": "port"}])

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

class _BaseExtractionModel(BaseModel):
    """공통 필드를 정의하는 베이스 클래스 (직접 사용 금지)"""
    model_config = ConfigDict(extra="ignore")

    name: str
    description: Optional[str] = None  # 대체 내용 정의 등
    global_rules: Optional[str] = None  # 전체적인 출력 형태/보정 정의
    data_structure: Optional[str] = "data"  # "table" (표), "data" (JSON), "report" (문서)
    model_type: Optional[str] = "extraction"  # "extraction" or "comparison"
    mapper_llm: Optional[str] = None  # LLM deployment name for fast structural tasks (e.g. gpt-4o-mini)
    extractor_llm: Optional[str] = None  # LLM deployment name for main extraction tasks (overrides default)
    webhook_url: Optional[str] = None  # POST URL for automation after extraction confirmation
    allowedGroups: Optional[List[str]] = None  # Access control groups
    fields: List[FieldDefinition]
    is_active: bool = True
    temperature: float = 0.0  # LLM Temperature (0.0 for deterministic)
    reference_data: Optional[Dict[str, Any]] = None  # 참고 데이터 (고객코드 매핑, 유효성 규칙 등)
    beta_features: Dict[str, bool] = Field(default_factory=default_beta_features)
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None
    dictionaries: Optional[List[str]] = None  # Dictionary categories for auto-normalization
    transform_rules: Optional[List[Dict[str, Any]]] = None  # Row expansion rules
    post_process_rules: List[PostProcessRule] = Field(default_factory=list)  # Stage 3
    vibe_dictionary: Optional[VibeDictionaryConfig] = None  # Stage 2

class ExtractionModel(_BaseExtractionModel):
    """DB에서 읽어온 모델 (id, azure_model_id 포함)"""
    id: str
    azure_model_id: Optional[str] = "prebuilt-layout"  # Azure Document Intelligence Model ID


class ExtractionModelCreate(_BaseExtractionModel):
    """모델 생성용 스키마 (id 자동 생성)"""
    pass

