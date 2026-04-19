// ==========================================
// EXTRACTION TYPES
// ==========================================

import { type ExtractionStatusType } from './constants/status'

/**
 * Canonical wrapper shape produced by backend `_validate_and_format`.
 * Every field in `guide_extracted` conforms to this contract.
 * Kept open (`unknown` value, all props optional) because pipelines
 * vary in what they populate.
 */
export interface ExtractedField {
    value: unknown
    original_value?: unknown
    confidence?: number
    bbox?: number[] | null
    page_number?: number
    validation_status?: string
    // Pipeline-specific extensions (Vibe Dictionary, DEX validation, etc.)
    // are attached ad-hoc by downstream code; `unknown` keeps callers honest.
    [extra: string]: unknown
}

export type GuideExtracted = Record<string, ExtractedField>

/**
 * Sub-document structure for multi-page document splitting
 */
export interface SubDocument {
    index: number
    type?: string // Document type (optional)
    page_range?: [number, number] // [start, end] page tuple
    page_ranges?: number[] // Legacy: individual page numbers
    filename?: string
    status: 'success' | 'error' | 'review_needed'
    data?: {
        guide_extracted: GuideExtracted
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- legacy shape, varies by pipeline
        raw_extracted?: Record<string, any>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- free-form unmapped data
        other_data: any[]
        raw_content?: string
        _beta_parsed_content?: string
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- bbox restoration map structure varies
        _beta_ref_map?: Record<string, any>
    }
}

/**
 * Preview data structure returned from extraction job
 */
export interface PreviewData {
    guide_extracted: GuideExtracted
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- legacy shape, varies by pipeline
    raw_extracted?: Record<string, any>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- free-form value
    other_data: Array<{ column: string; value: any; confidence?: number; bbox?: number[] }>
    model_fields: Array<{ key: string; label: string }>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw backend debug blob
    debug_data?: any
    sub_documents?: SubDocument[]
    raw_content?: string // Raw text from Document Intelligence
    _beta_parsed_content?: string // Parsed text from LayoutParser
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- bbox restoration map varies
    _beta_ref_map?: Record<string, any>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw DI table cells
    raw_tables?: any[]
    comparison_result?: {
        differences: Array<{
            id: string | number
            description: string
            category: string
            location_1: number[] | null
            location_2: number[] | null
            page_number?: number
        }>
        error?: string
    }
    comparisons?: Array<{
        candidate_index: number
        result: {
            differences: Array<{
                id: string | number
                description: string
                category: string
                location_1: number[] | null
                location_2: number[] | null
            }>
            error?: string
        }
        file_url?: string
        error?: string
    }>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- DEX validation payload evolving
    __dex_validation__?: any
}

// Comparison Settings Types
export interface ComparisonSettings {
    confidence_threshold: number; // 0.85
    ignore_position_changes: boolean; // true
    ignore_color_changes: boolean; // false
    ignore_font_changes: boolean; // true
    ignore_compression_noise: boolean; // true - JPEG/image compression artifacts
    custom_ignore_rules?: string; // custom instructions
    // Method Toggles
    use_ssim_analysis?: boolean; // Default true
    use_vision_analysis?: boolean; // Default true
    // Category customization
    allowed_categories?: string[]; // If set, only use these categories
    excluded_categories?: string[]; // If set, exclude these categories
}

export interface ExcelExportColumn {
    key: string;
    label: string;
    width: number;
    enabled: boolean;
}

/**
 * Extraction model definition
 */
export interface ExtractionModel {
    id: string
    name: string
    description: string
    fields: Array<{ key: string; label: string; type?: string }>
    allowedGroups?: string[]
    model_type?: 'extraction' | 'comparison'
    comparison_settings?: ComparisonSettings
    excel_columns?: ExcelExportColumn[]
    beta_features?: {
        use_optimized_prompt?: boolean
        use_virtual_excel_ocr?: boolean
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- flag set grows organically
        [key: string]: any
    }
}

/**
 * Field highlight for PDF viewer
 */
export interface Highlight {
    fieldKey: string
    content: string
    pageIndex: number
    fileId?: string // Linked file ID for multi-file context
    position: {
        boundingRect: {
            x1: number
            y1: number
            x2: number
            y2: number
            width: number
            height: number
        }
    }
}

/**
 * Extraction log record from database
 */
export interface ExtractionLog {
    id: string
    model_id: string
    model_name?: string // Optional, for global view/UI
    user_id: string
    user_name?: string
    user_email?: string
    filename: string
    file_url?: string
    candidate_file_urls?: string[] // For comparison models
    status: ExtractionStatusType | string // Allow dynamic string fallback but prefer typed
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- stored extracted shape varies by model
    extracted_data?: Record<string, any>
    preview_data?: PreviewData // For in-progress jobs
    job_id?: string // For in-progress jobs
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw backend debug blob
    debug_data?: any
    error?: string
    created_at: string
    updated_at?: string
}

// ==========================================
// VIEW TYPES
// ==========================================

export type ViewStep = 'history' | 'upload' | 'raw_data' | 'refined_data'
export type ExtractionStatus = ExtractionStatusType | 'idle'
