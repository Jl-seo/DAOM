
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
        other_data: any[]
    }
}

/**
 * Preview data structure returned from extraction job
 */
export interface PreviewData {
    guide_extracted: Record<string, any>
    other_data: Array<{ column: string; value: any; confidence?: number; bbox?: number[] }>
    model_fields: Array<{ key: string; label: string }>
    sub_documents?: SubDocument[]
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
}

/**
 * Field highlight for PDF viewer
 */
export interface Highlight {
    fieldKey: string
    content: string
    pageIndex: number
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
    status: ExtractionStatusType | string // Allow dynamic string fallback but prefer typed
    extracted_data?: Record<string, any>
    preview_data?: PreviewData // For in-progress jobs
    job_id?: string // For in-progress jobs
    error?: string
    created_at: string
    updated_at?: string
}

// ==========================================
// VIEW TYPES
// ==========================================

export type ViewStep = 'history' | 'upload' | 'review' | 'complete'
export type ExtractionStatus = ExtractionStatusType | 'idle'
