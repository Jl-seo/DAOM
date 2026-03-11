/* eslint-disable @typescript-eslint/no-explicit-any */
// Status codes matching backend enum (backend/app/core/enums.py)
export type ExtractionStatus =
    // Processing states (P-Series)
    | 'P100'  // PENDING - Initial state
    | 'P200'  // UPLOADING - File uploading to storage
    | 'P300'  // ANALYZING - OCR / Doc Intelligence analysis
    | 'P400'  // REFINING - LLM processing / Refining
    // Success states (S-Series)
    | 'S100'  // SUCCESS - Completed successfully
    // Error states (E-Series)
    | 'E100'  // FAILED - Extraction failed
    | 'E200'  // ERROR - System error
    // Legacy string values (for backward compatibility)
    | 'pending' | 'uploading' | 'processing' | 'analyzing' | 'completed' | 'success' | 'failed' | 'error' | 'cancelled'

export interface ExtractionJob {
    job_id: string
    id?: string
    status: ExtractionStatus
    filename: string
    upload_time: string
    completion_time?: string
    error?: string
    preview_data?: {
        sub_documents?: Array<{
            index: number
            status: string
            data: {
                guide_extracted: Record<string, any>
            }
        }>
    }
}
