/* eslint-disable @typescript-eslint/no-explicit-any */
import { FIELD_TYPES, DATA_STRUCTURES } from '../constants'

export type FieldType = typeof FIELD_TYPES[number]['value']
export type DataStructureType = typeof DATA_STRUCTURES[number]['id']

export interface Field {
    key: string
    label: string
    description: string
    rules: string
    type: FieldType
    is_dex_target?: boolean
    dictionary?: string // Field-level dictionary mapping category (e.g., "port", "charge")
}

export interface ComparisonSettings {
    confidence_threshold: number
    ignore_position_changes: boolean
    ignore_color_changes: boolean
    ignore_font_changes: boolean
    ignore_compression_noise: boolean
    custom_ignore_rules?: string
    output_language?: string
    use_ssim_analysis?: boolean
    use_vision_analysis?: boolean
    align_images?: boolean
    allowed_categories?: string[]
    excluded_categories?: string[]
    custom_categories?: { key: string; label: string; description: string }[]
    ssim_identity_threshold?: number  // Global SSIM score gate (0.90~1.0, default 0.95)
}

export interface ExcelExportColumn {
    key: string
    label: string
    width: number
    enabled: boolean
}

export interface Model {
    id: string
    name: string
    description: string
    global_rules: string
    data_structure: DataStructureType
    model_type?: 'extraction' | 'comparison'
    webhook_url?: string  // POST URL for automation after extraction
    fields: Field[]
    is_active?: boolean  // 메뉴에서 숨기기 (false면 숨김)
    reference_data?: Record<string, unknown>  // 참고 데이터 (고객코드 매핑, 유효성 규칙 등)
    transformation_config?: {
        natural_language_rule?: string
        parsed_rules?: any[]
        last_updated?: string
    }
    comparison_settings?: ComparisonSettings
    excel_columns?: ExcelExportColumn[]
    beta_features?: BetaFeatures
    dictionaries?: string[]  // Dictionary categories for auto-normalization (e.g., ["port", "charge"])
    transform_rules?: TransformRule[]  // Row expansion rules (e.g., group code → individual ports)
}

export interface TransformRule {
    name: string
    target_field: string
    match_field: string
    match_value: string
    expand_field: string
    expand_values: string[]
    expand_codes?: string[]
    code_field?: string
}

/**
 * Beta feature toggles - matches backend default_beta_features()
 * Frontend should use getBetaFeatures() helper for safe access with defaults
 */
export interface BetaFeatures {
    use_optimized_prompt?: boolean
    use_virtual_excel_ocr?: boolean
    use_vision_extraction?: boolean
    use_dex_validation?: boolean
}

/**
 * Get beta features with defaults applied.
 * Ensures symmetry with backend Pydantic default_factory.
 */
export function getBetaFeatures(model: Model | undefined): BetaFeatures {
    return {
        use_optimized_prompt: model?.beta_features?.use_optimized_prompt ?? false,
        use_virtual_excel_ocr: model?.beta_features?.use_virtual_excel_ocr ?? false,
        use_vision_extraction: model?.beta_features?.use_vision_extraction ?? false,
        use_dex_validation: model?.beta_features?.use_dex_validation ?? false
    }
}

