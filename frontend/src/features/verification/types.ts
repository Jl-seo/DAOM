/* eslint-disable @typescript-eslint/no-explicit-any */

// ==========================================
// EXTRACTION TYPES
// ==========================================

import { type ExtractionStatusType } from './constants/status'

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
        guide_extracted: Record<string, any>
        raw_extracted?: Record<string, any>
        other_data: any[]
        raw_content?: string
        _beta_parsed_content?: string
        _beta_ref_map?: Record<string, any>
        extracted_data?: any[] // Export-mapped flat table
    }
}

/**
 * Preview data structure returned from extraction job
 */
export interface PreviewData {
    guide_extracted: Record<string, any>
    raw_extracted?: Record<string, any>
    other_data: Array<{ column: string; value: any; confidence?: number; bbox?: number[] }>
    model_fields: Array<{ key: string; label: string }>
    extracted_data?: any[] // Export-mapped flat table
    debug_data?: any // Raw debug information from backend
    sub_documents?: SubDocument[]
    raw_content?: string // Raw text from Document Intelligence
    _beta_parsed_content?: string // Parsed text from LayoutParser
    _beta_ref_map?: Record<string, any> // BBox restoration map
    raw_tables?: any[] // Raw table data from Document Intelligence
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
    extracted_data?: Record<string, any>
    preview_data?: PreviewData // For in-progress jobs
    job_id?: string // For in-progress jobs
    debug_data?: any // Raw debug data from backend
    error?: string
    created_at: string
    updated_at?: string
}

// ==========================================
// VIEW TYPES
// ==========================================

export type ViewStep = 'history' | 'upload' | 'raw_data' | 'refined_data' | 'aggregated_data'
export type ExtractionStatus = ExtractionStatusType | 'idle'
