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
    comparison_settings?: ComparisonSettings
    excel_columns?: ExcelExportColumn[]
}
