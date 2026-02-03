import { FIELD_TYPES, DATA_STRUCTURES } from '../constants'

export type FieldType = typeof FIELD_TYPES[number]['value']
export type DataStructureType = typeof DATA_STRUCTURES[number]['id']

export interface Field {
    key: string
    label: string
    description: string
    rules: string
    type: FieldType
}

export interface ComparisonSettings {
    confidence_threshold: number
    ignore_position_changes: boolean
    ignore_color_changes: boolean
    ignore_font_changes: boolean
    ignore_compression_noise: boolean
    custom_ignore_rules?: string
    allowed_categories?: string[]
    excluded_categories?: string[]
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
    comparison_settings?: ComparisonSettings
    excel_columns?: ExcelExportColumn[]
}
