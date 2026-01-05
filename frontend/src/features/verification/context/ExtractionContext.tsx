import { createContext, useContext, useState, useRef, type ReactNode, useCallback, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api'
import { EXTRACTION_STATUS, isSuccessStatus, isErrorStatus, isReviewNeededStatus } from '../constants/status'
import type {
    ViewStep,
    ExtractionStatus,
    SubDocument,
    PreviewData,
    ExtractionModel,
    Highlight,
    ExtractionLog
} from '../types'
import { POLLING_INTERVAL_MS } from '../constants'

// Re-export types for backward compatibility
export type { ViewStep, ExtractionStatus, SubDocument, PreviewData, ExtractionModel, Highlight, ExtractionLog }

// Context Value Interface
interface ExtractionContextValue {
    // Model
    model: ExtractionModel | null
    setModel: (model: ExtractionModel | null) => void

    // Step Navigation
    activeStep: ViewStep
    setActiveStep: (step: ViewStep) => void

    // Status
    status: ExtractionStatus
    setStatus: (status: ExtractionStatus) => void

    // File
    file: File | null
    setFile: (file: File | null) => void
    fileUrl: string | null
    setFileUrl: (url: string | null) => void
    isDragging: boolean
    setIsDragging: (dragging: boolean) => void
    filename: string | null
    setFilename: (name: string | null) => void

    // Job & Log tracking
    currentJobId: string | null
    setCurrentJobId: (id: string | null) => void
    currentLogId: string | null
    setCurrentLogId: (id: string | null) => void

    // Preview Data
    previewData: PreviewData | null
    setPreviewData: (data: PreviewData | null) => void

    // Multi-doc
    selectedSubDocIndex: number
    setSelectedSubDocIndex: (index: number) => void

    // Extracted Result
    result: Record<string, any> | null
    setResult: (result: Record<string, any> | null) => void

    // UI State
    selectedFieldKey: string | null
    setSelectedFieldKey: (key: string | null) => void
    error: string | null
    setError: (error: string | null) => void

    // Highlights for PDF
    highlights: Highlight[]

    // Actions
    processFile: (file: File) => Promise<void>
    handleConfirmSelection: (selectedColumns: string[], editedGuideData?: Record<string, any>, editedOtherData?: any[]) => void
    handleRetry: () => void
    handleReset: () => void
    handleCancelPreview: () => void
    loadFromHistory: (log: ExtractionLog) => void
    resumeJob: (jobId: string, fileUrl?: string, status?: ExtractionStatus) => void // New: Resume in-progress job
}

const ExtractionContext = createContext<ExtractionContextValue | null>(null)

export function useExtraction() {
    const context = useContext(ExtractionContext)
    if (!context) {
        throw new Error('useExtraction must be used within ExtractionProvider')
    }
    return context
}

interface ExtractionProviderProps {
    modelId: string
    children: ReactNode
}

export function ExtractionProvider({ modelId, children }: ExtractionProviderProps) {
    // Model state
    const [model, setModel] = useState<ExtractionModel | null>(null)

    // Navigation
    const [activeStep, setActiveStep] = useState<ViewStep>('history')

    // Status
    const [status, setStatus] = useState<ExtractionStatus>('idle')

    // File
    const [file, setFile] = useState<File | null>(null)
    const [fileUrl, setFileUrl] = useState<string | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [filename, setFilename] = useState<string | null>(null)

    // Job tracking (for DB integration)
    const [currentJobId, setCurrentJobId] = useState<string | null>(null)
    const [currentLogId, setCurrentLogId] = useState<string | null>(null)

    // Data
    const [previewData, setPreviewData] = useState<PreviewData | null>(null)
    const [selectedSubDocIndex, setSelectedSubDocIndex] = useState(0)
    const [result, setResult] = useState<Record<string, any> | null>(null)

    // UI
    const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)

    // Polling ref
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

    // Compute highlights from preview data
    const highlights: Highlight[] = useMemo(() => {
        console.log('[Highlights] previewData:', previewData ? Object.keys(previewData) : null)
        console.log('[Highlights] sub_documents:', previewData?.sub_documents?.length)

        if (!previewData?.guide_extracted && !previewData?.sub_documents) return []

        const currentData = previewData.sub_documents && previewData.sub_documents.length > 0
            ? previewData.sub_documents[selectedSubDocIndex]?.data?.guide_extracted
            : previewData.guide_extracted

        console.log('[Highlights] currentData keys:', currentData ? Object.keys(currentData) : null)
        if (currentData) {
            const sampleKey = Object.keys(currentData)[0]
            console.log('[Highlights] sample field:', sampleKey, currentData[sampleKey])
        }

        if (!currentData) return []

        return Object.entries(currentData)
            .filter(([_, value]) => {
                const data = typeof value === 'object' && value && 'bbox' in value ? value : null
                // Support both old array format and new object format
                return data?.bbox && (
                    (Array.isArray(data.bbox) && data.bbox.length >= 4) ||
                    (typeof data.bbox === 'object' && 'x1' in data.bbox)
                )
            })
            .map(([key, value]) => {
                const data = value as { value: any; bbox: any; confidence?: number; page_number?: number; low_confidence?: boolean }
                // Backend returns 1-based page number, viewer needs 0-based index
                const pageIndex = data.page_number ? data.page_number - 1 : 0

                // Handle both array [x1, y1, x2, y2] and object {x1, y1, width, height} formats
                let boundingRect
                if (Array.isArray(data.bbox)) {
                    const [x1, y1, x2, y2] = data.bbox
                    boundingRect = { x1, y1, x2, y2, width: x2 - x1, height: y2 - y1 }
                } else {
                    const { x1, y1, width, height } = data.bbox
                    boundingRect = { x1, y1, x2: x1 + width, y2: y1 + height, width, height }
                }

                return {
                    fieldKey: key,
                    content: String(data.value),
                    pageIndex: pageIndex,
                    position: { boundingRect }
                }
            })
    }, [previewData, selectedSubDocIndex])

    // Polling attempt counter ref
    const pollingAttemptsRef = useRef(0)
    const MAX_POLLING_ATTEMPTS = 60 // ~5 minutes at 5 second intervals

    // Start polling for job status
    const startPolling = useCallback((jobId: string) => {
        if (pollingRef.current) clearInterval(pollingRef.current)
        pollingAttemptsRef.current = 0

        pollingRef.current = setInterval(async () => {
            pollingAttemptsRef.current += 1

            // Timeout protection
            if (pollingAttemptsRef.current > MAX_POLLING_ATTEMPTS) {
                console.warn('[Polling] Max attempts reached, stopping')
                clearInterval(pollingRef.current!)
                pollingRef.current = null
                setStatus(EXTRACTION_STATUS.ERROR)
                setError('처리 시간이 초과되었습니다. 다시 시도해 주세요.')
                toast.error('처리 시간 초과')
                return
            }

            try {
                const res = await apiClient.get(`/extraction/job/${jobId}`)
                const job = res.data

                console.log('[Polling] Job status:', job.status, `(attempt ${pollingAttemptsRef.current})`)
                console.log('[Polling] Job preview_data keys:', job.preview_data ? Object.keys(job.preview_data) : 'NULL')

                // Check for completion (either PREVIEW_READY or SUCCESS)
                if (isReviewNeededStatus(job.status) || isSuccessStatus(job.status)) {
                    clearInterval(pollingRef.current!)
                    pollingRef.current = null

                    // Handle array or object response
                    const raw = job.preview_data
                    const preview = Array.isArray(raw)
                        ? { guide_extracted: raw[0] || {}, other_data: [], model_fields: model?.fields || [] }
                        : { ...raw, model_fields: raw?.model_fields || model?.fields || [] }

                    console.log('[Polling] Setting previewData:', JSON.stringify(preview)?.slice(0, 300))
                    setPreviewData(preview)
                    setStatus(EXTRACTION_STATUS.SUCCESS) // Treat as success
                    setActiveStep('review') // Show review view

                    // Set log_id for retry functionality
                    if (job.log_id) {
                        setCurrentLogId(job.log_id)
                    }
                } else if (isErrorStatus(job.status)) {
                    clearInterval(pollingRef.current!)
                    pollingRef.current = null
                    setStatus(EXTRACTION_STATUS.ERROR)
                    setError(job.error || '추출 실패')
                    toast.error('추출 실패: ' + (job.error || '알 수 없는 오류'))

                    // Set log_id even on error for potential retry
                    if (job.log_id) {
                        setCurrentLogId(job.log_id)
                    }
                }
            } catch (e: any) {
                console.error('[Polling] Error:', e)
                // Stop polling on 404 - job doesn't exist (expired or invalid)
                if (e?.response?.status === 404) {
                    clearInterval(pollingRef.current!)
                    pollingRef.current = null
                    setStatus(EXTRACTION_STATUS.ERROR)
                    setError('작업을 찾을 수 없습니다. 목록으로 돌아가서 다시 시도해 주세요.')
                    toast.error('작업을 찾을 수 없습니다')
                    setActiveStep('history')
                }
                // Stop polling on 500 errors after a few attempts
                if (e?.response?.status >= 500 && pollingAttemptsRef.current > 3) {
                    clearInterval(pollingRef.current!)
                    pollingRef.current = null
                    setStatus(EXTRACTION_STATUS.ERROR)
                    setError('서버 오류가 발생했습니다.')
                    toast.error('서버 오류')
                }
            }
        }, POLLING_INTERVAL_MS)
    }, [model?.fields]) // Dependencies for polling interval content

    // File processing
    const processFile = useCallback(async (selectedFile: File) => {
        // Clear any existing polling first
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }

        setFile(selectedFile)
        setFilename(selectedFile.name)
        setStatus(EXTRACTION_STATUS.UPLOADING)
        setError(null)
        setResult(null)
        setCurrentLogId(null)
        setCurrentJobId(null)

        const formData = new FormData()
        formData.append('file', selectedFile)
        formData.append('model_id', modelId)

        try {
            const res = await apiClient.post('/extraction/start-job', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            })

            const { job_id, file_url, log_id } = res.data
            setCurrentJobId(job_id)
            setFileUrl(file_url)
            if (log_id) setCurrentLogId(log_id)  // Enable retry functionality
            setStatus(EXTRACTION_STATUS.REFINING)
            startPolling(job_id)
        } catch (e: any) {
            setStatus(EXTRACTION_STATUS.ERROR)
            setError(e?.response?.data?.detail || '파일 업로드 실패')
            toast.error('파일 업로드 실패')
        }
    }, [modelId, startPolling])

    // Confirm extraction mutation
    const saveLogMutation = useMutation({
        mutationFn: async ({ editedGuideData, editedOtherData }: { editedGuideData?: Record<string, any>, editedOtherData?: any[] }) => {
            if (!currentLogId) throw new Error('No log ID')
            if (!model) throw new Error('No model active')

            // Start with existing guide_extracted
            const currentGuide = previewData?.sub_documents && previewData.sub_documents.length > 0
                ? previewData.sub_documents[selectedSubDocIndex]?.data?.guide_extracted || {}
                : previewData?.guide_extracted || {}

            const finalData = { ...currentGuide, ...(editedGuideData || {}) }

            // Clean up values
            Object.keys(finalData).forEach(key => {
                const val = finalData[key]
                if (val && typeof val === 'object' && 'value' in val) {
                    finalData[key] = val.value
                }
            })

            // Merge other data
            if (editedOtherData && Array.isArray(editedOtherData)) {
                editedOtherData.forEach(item => {
                    if (item.column && item.value !== undefined) {
                        const key = typeof item.column === 'object' ? JSON.stringify(item.column) : String(item.column)
                        finalData[key] = item.value
                    }
                })
            }

            const payload = {
                model_id: model.id,
                filename: filename || 'unknown.pdf',
                file_url: fileUrl || '',
                guide_extracted: finalData,
                other_data: editedOtherData || [],
                log_id: currentLogId
            }

            const res = await apiClient.post('/extraction/save-extraction', payload)
            return res.data
        },
        onSuccess: (data) => {
            setResult(data.extracted_data)
            console.log('[AutoSave] Historical log updated successfully')
        },
        onError: (err: any) => {
            toast.error('저장 실패: ' + (err?.message || '알 수 없는 오류'))
        }
    })

    // Confirm extraction mutation
    const confirmJobMutation = useMutation({
        mutationFn: async ({ editedGuideData, editedOtherData }: { editedGuideData?: Record<string, any>, editedOtherData?: any[] }) => {
            if (!currentJobId) throw new Error('No active job')

            // Start with existing guide_extracted as base to prevent data loss
            const currentGuide = previewData?.sub_documents && previewData.sub_documents.length > 0
                ? previewData.sub_documents[selectedSubDocIndex]?.data?.guide_extracted || {}
                : previewData?.guide_extracted || {}

            // Merge edited guide data over existing
            const finalData = { ...currentGuide, ...(editedGuideData || {}) }

            // Clean up values: extract raw values from {value, confidence} objects
            Object.keys(finalData).forEach(key => {
                const val = finalData[key]
                if (val && typeof val === 'object' && 'value' in val) {
                    finalData[key] = val.value
                }
            })

            // Merge other data
            if (editedOtherData && Array.isArray(editedOtherData)) {
                editedOtherData.forEach(item => {
                    if (item.column) {
                        const key = typeof item.column === 'object' ? JSON.stringify(item.column) : String(item.column)
                        // Only add if value exists
                        if (item.value !== undefined) {
                            finalData[key] = item.value
                        }
                    }
                })
            }

            const res = await apiClient.post(`/extraction/confirm-job/${currentJobId}`, {
                edited_data: finalData
            })
            return res.data
        },
        onSuccess: (data) => {
            setResult(data.extracted_data)
            // Don't change step or show toast for auto-save
            console.log('[AutoSave] Saved successfully')
        },
        onError: (err: any) => {
            toast.error('저장 실패: ' + (err?.message || '알 수 없는 오류'))
        }
    })

    const handleConfirmSelection = useCallback((
        _selectedColumns: string[],
        editedGuideData?: Record<string, any>,
        editedOtherData?: any[]
    ) => {
        // Guard: Skip if no active job AND no log ID
        if (!currentJobId && !currentLogId) {
            console.log('[AutoSave] Skipped - no active job and no log ID')
            return
        }

        if (currentJobId) {
            confirmJobMutation.mutate({ editedGuideData, editedOtherData })
        } else {
            // Historical record update
            saveLogMutation.mutate({ editedGuideData, editedOtherData })
        }
    }, [currentJobId, currentLogId, confirmJobMutation, saveLogMutation])

    // Retry mutation
    const retryMutation = useMutation({
        mutationFn: async () => {
            if (!currentLogId) throw new Error('No log to retry')
            const res = await apiClient.post(`/extraction/retry/${currentLogId}`)
            return res.data
        },
        onSuccess: (data) => {
            setCurrentJobId(data.job_id)
            setFileUrl(data.file_url)
            setStatus(EXTRACTION_STATUS.REFINING)
            setActiveStep('upload')  // Shows the loading/processing view
            startPolling(data.job_id)
            toast.info('재추출을 시작합니다...')
        },
        onError: (error: any) => {
            const errorMsg = error?.response?.data?.detail || error?.message || '재시도 실패'
            toast.error(`재시도 실패: ${errorMsg}`)
            console.error('[Retry] Error:', error)
        }
    })

    const handleRetry = useCallback(() => {
        if (currentLogId) {
            retryMutation.mutate()
        } else if (file) {
            processFile(file)
        } else {
            toast.error('재시도할 수 없습니다. 목록에서 다시 선택해 주세요.')
        }
    }, [currentLogId, file, retryMutation, processFile])

    const handleReset = useCallback(() => {
        setFile(null)
        setFileUrl(null)
        setPreviewData(null)
        setResult(null)
        setStatus('idle')
        setCurrentJobId(null)
        setCurrentLogId(null)
        setSelectedSubDocIndex(0)
        setActiveStep('upload')
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }
    }, [])

    const handleCancelPreview = useCallback(() => {
        // Since jobs are asynchronous, we just clear local state and go back to history.
        // The job continues in the background.
        handleReset()
        setActiveStep('history')
    }, [handleReset])

    const resumeJob = useCallback((jobId: string, url?: string, jobStatus?: ExtractionStatus) => {
        console.log('[resumeJob] Resuming job:', jobId)
        setCurrentJobId(jobId)
        if (url) setFileUrl(url)

        // Determine state based on status
        if (jobStatus === EXTRACTION_STATUS.PREVIEW_READY) {
            // If ready, start polling to fetch data immediately (or we could fetch directly)
            startPolling(jobId)
            setStatus(EXTRACTION_STATUS.REFINING) // Short loading state until poll returns
        } else {
            setStatus(EXTRACTION_STATUS.REFINING)
            startPolling(jobId)
        }

        setActiveStep('upload') // Start polling will switch to 'review' when ready
    }, [startPolling])

    const loadFromHistory = useCallback((log: ExtractionLog) => {
        console.log('[loadFromHistory] Loading log:', { id: log.id, file_url: log.file_url, filename: log.filename })
        setResult(log.extracted_data || null)
        setStatus(isSuccessStatus(log.status) ? EXTRACTION_STATUS.COMPLETE : EXTRACTION_STATUS.ERROR)
        setFileUrl(log.file_url || null)
        setFile(null) // No file object when loading from history
        setFilename(log.filename)
        setCurrentLogId(log.id)


        // Use saved preview_data if available (preserves other_data structure)
        // Otherwise fall back to reconstructing from extracted_data
        console.log('[loadFromHistory] preview_data:', JSON.stringify(log.preview_data, null, 2)?.slice(0, 500))
        console.log('[loadFromHistory] extracted_data:', JSON.stringify(log.extracted_data, null, 2)?.slice(0, 500))
        if (log.preview_data) {
            setPreviewData({
                ...log.preview_data,
                model_fields: log.preview_data.model_fields || model?.fields?.map(f => ({ key: f.key, label: f.label })) || []
            })
        } else {
            // Legacy: Reconstruct minimal preview from extracted_data
            setPreviewData({
                guide_extracted: log.extracted_data || {},
                other_data: [],
                model_fields: model?.fields?.map(f => ({ key: f.key, label: f.label })) || []
            })
        }

        setActiveStep('complete')
    }, [model?.fields])

    const value: ExtractionContextValue = useMemo(() => ({
        model, setModel,
        activeStep, setActiveStep,
        status, setStatus,
        file, setFile,
        fileUrl, setFileUrl,
        filename, setFilename,
        isDragging, setIsDragging,
        currentJobId, setCurrentJobId,
        currentLogId, setCurrentLogId,
        previewData, setPreviewData,
        selectedSubDocIndex, setSelectedSubDocIndex,
        result, setResult,
        selectedFieldKey, setSelectedFieldKey,
        error, setError,
        highlights,
        processFile,
        handleConfirmSelection,
        handleRetry,
        handleReset,
        handleCancelPreview,
        loadFromHistory,
        resumeJob
    }), [
        model, activeStep, status, file, fileUrl, filename, isDragging,
        currentJobId, currentLogId, previewData, selectedSubDocIndex,
        result, selectedFieldKey, error, highlights,
        processFile, handleConfirmSelection, handleRetry, handleReset,
        handleCancelPreview, loadFromHistory, resumeJob
    ])

    return (
        <ExtractionContext.Provider value={value}>
            {children}
        </ExtractionContext.Provider>
    )
}
