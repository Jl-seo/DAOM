from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Union
from pydantic import model_validator
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
    SPLIT_DELIMITER = "split_delimiter"

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
    hit_count: int = 1

class LearningMode(str, Enum):
    AUTO = "auto_apply"
    MANUAL = "manual_approval"

class VibeDictionaryConfig(BaseModel):
    enabled: bool = False
    persona_prompt: str = ""
    target_fields: List[str] = []
    learning_mode: LearningMode = LearningMode.MANUAL


class FieldType(str, Enum):
    """허용된 필드 타입 — free-form string 대신 enum으로 제한"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ARRAY = "array"
    TABLE = "table"
    LIST = "list"
    OBJECT = "object"


class InheritanceSource(str, Enum):
    """field_inheritance 값에 사용하는 표준 소스 경로"""
    DOCUMENT_CURRENCY = "document.currency"
    BLOCK_CONTEXT_POL = "block_context.POL"
    BLOCK_CONTEXT_POD = "block_context.POD"
    BLOCK_CONTEXT_CURRENCY = "block_context.Currency"
    SECTION_VALIDITY_START = "section.validity.start_date"
    SECTION_VALIDITY_END = "section.validity.end_date"
    SECTION_ORIGIN = "section.origin_port"
    GROUP_LABEL = "group.label"


class SubFieldDefinition(BaseModel):
    """테이블/리스트 필드의 하위 컬럼 정의"""
    key: str
    label: str
    type: str = "string"
    description: Optional[str] = None
    rules: Optional[str] = None
    dictionary: Optional[str] = None  # semantic category (e.g., "port", "charge", "currency")
    required: bool = False
    validation_regex: Optional[str] = None


class FieldDefinition(BaseModel):
    key: str
    label: str
    description: Optional[str] = None  # 자연어 정의 (무엇을 추출할지)
    rules: Optional[str] = None  # 출력 보정/형태 정의 (자연어)
    type: str = "string"  # FieldType enum 값 사용 권장, 하위호환 위해 str 유지
    is_dex_target: Optional[bool] = False # DEX 바코드 검증 타겟 여부
    dictionary: Optional[str] = None # Field-level dictionary mapping category (e.g., "port", "charge")
    required: bool = False # 필수 항목 추출 여부
    is_pii: bool = False # 개인정보 필드 여부 (마스킹 대상)
    validation_regex: Optional[str] = None # 값 검증 정규식 (e.g., ^[A-Z0-9]+$)
    sub_fields: Optional[List[Dict[str, Any]]] = None  # 항상 plain dict로 저장 (JSON 직렬화 안전)
    # Row classification rules (table/list fields only)
    include_when: Optional[List[str]] = None  # Row 포함 조건 (자연어 리스트, e.g. ["row has freight amount columns"])
    exclude_when: Optional[List[str]] = None  # Row 제외 조건 (자연어 리스트, e.g. ["row is only a group header"])
    group_row_behavior: Optional[str] = None  # "context_label" | "skip" | "prefix_to_children"
    field_inheritance: Optional[Dict[str, str]] = None  # Sub-field → source 매핑 (InheritanceSource 값 사용 권장)

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "FieldDefinition":
        """Ensure sub_fields are always plain dicts, never Pydantic model instances."""
        if isinstance(obj, dict) and obj.get("sub_fields"):
            obj = dict(obj)  # shallow copy
            obj["sub_fields"] = [
                sf.model_dump() if hasattr(sf, 'model_dump') else (sf if isinstance(sf, dict) else vars(sf))
                for sf in obj["sub_fields"] if sf
            ]
        return super().model_validate(obj, **kwargs)

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

class PivotTableDef(BaseModel):
    table: str
    category_field: str
    subcategory_field: str
    value_field: str
    column_naming: str

class ColumnMappingDef(BaseModel):
    target: str
    source: str

class ExportDefinition(BaseModel):
    base_table: str
    merge_keys: List[str] = []
    pivot_tables: List[PivotTableDef] = []
    final_column_mappings: List[ColumnMappingDef] = []
    conflict_policy: str = "first_non_empty"
    # [Phase 3.5] Aggregation & Metadata Injection
    group_by_keys: List[str] = []  # List of final column names to group by
    aggregation_strategy: str = "first_non_empty"  # Strategy for merging logical rows (first_non_empty, concat)
    inject_metadata: bool = False  # If true, PA metadata values will be appended to every row

    @model_validator(mode='before')
    @classmethod
    def migrate_mappings(cls, data: Any) -> Any:
        if isinstance(data, dict) and "final_column_mappings" in data:
            mappings = data["final_column_mappings"]
            if isinstance(mappings, dict):
                data["final_column_mappings"] = [{"target": k, "source": v} for k, v in mappings.items()]
        return data

class ExportConfig(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = None
    definition: ExportDefinition


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
    retention_days: Optional[int] = None  # 데이터 보관 주기 (일 단위, None이면 무기한)
    temperature: float = 0.0  # LLM Temperature (0.0 for deterministic)
    reference_data: Optional[Dict[str, Any]] = None  # 참고 데이터 (고객코드 매핑, 유효성 단어 등)
    beta_features: Dict[str, bool] = Field(default_factory=default_beta_features)
    comparison_settings: Optional[ComparisonSettings] = None
    excel_columns: Optional[List[ExcelExportColumn]] = None
    dictionaries: Optional[List[str]] = None  # Dictionary categories for auto-normalization
    transform_rules: Optional[List[Dict[str, Any]]] = None  # Row expansion rules
    post_process_rules: List[PostProcessRule] = Field(default_factory=list)  # Stage 3
    vibe_dictionary: Optional[VibeDictionaryConfig] = None  # Stage 2
    export_config: Optional[ExportConfig] = None  # Export Engine Configuration

class ExtractionModel(_BaseExtractionModel):
    """DB에서 읽어온 모델 (id, azure_model_id 포함)"""
    id: str
    azure_model_id: Optional[str] = "prebuilt-layout"  # Azure Document Intelligence Model ID


class ExtractionModelCreate(_BaseExtractionModel):
    """모델 생성용 스키마 (id 자동 생성)"""
    pass

