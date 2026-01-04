export type ExtractionStatus = 'pending' | 'uploading' | 'processing' | 'analyzing' | 'completed' | 'success' | 'failed' | 'error'

export interface ExtractionJob {
    job_id: string
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
