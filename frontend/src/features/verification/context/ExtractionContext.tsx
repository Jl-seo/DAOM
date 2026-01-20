import { createContext, useContext, useState, useRef, type ReactNode, useCallback, useMemo, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api'
import { EXTRACTION_STATUS, isSuccessStatus } from '../constants/status'
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

// Development-only logging helper
const devLog = (...args: any[]) => {
    if (import.meta.env.DEV) {
        console.log(...args)
    }
}

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
    candidateFiles: File[] | null // NEW: Array
    setCandidateFiles: (files: File[] | null) => void
    fileUrl: string | null
    candidateFileUrls?: string[] | null // NEW: Array
    candidateFileUrl: string | null // Legacy/Convenience: First candidate URL
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
    processFile: (file: File, candidateFiles?: File[]) => Promise<void>
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
    const [candidateFiles, setCandidateFiles] = useState<File[] | null>(null) // CHANGED: Single -> Array
    const [fileUrl, setFileUrl] = useState<string | null>(null)
    const [candidateFileUrls, setCandidateFileUrls] = useState<string[] | null>(null) // CHANGED: Single -> Array
    const [isDragging, setIsDragging] = useState(false)
    const [filename, setFilename] = useState<string | null>(null)

    // State for Job & Log tracking
    const [currentJobId, setCurrentJobId] = useState<string | null>(null)
    const [currentLogId, setCurrentLogId] = useState<string | null>(null)

    // State for Preview Data & Results
    const [previewData, setPreviewData] = useState<PreviewData | null>(null)
    const [result, setResult] = useState<Record<string, any> | null>(null)
    const [selectedSubDocIndex, setSelectedSubDocIndex] = useState(0)

    // UI Interactive State
    const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [highlights, setHighlights] = useState<Highlight[]>([])

    // Compute highlights from previewData
    useEffect(() => {
        if (!previewData) {
            setHighlights([])
            return
        }

        const currentData = previewData.sub_documents && previewData.sub_documents.length > 0
            ? previewData.sub_documents[selectedSubDocIndex]?.data?.guide_extracted
            : previewData.guide_extracted

        if (!currentData) {
            setHighlights([])
            return
        }

        // Debug: Log the current data to trace bbox issues
        devLog('[Highlights] currentData keys:', Object.keys(currentData))
        devLog('[Highlights] Sample field data:', Object.entries(currentData).slice(0, 2).map(([k, v]) => ({ key: k, hasBbox: !!(v as any)?.bbox, bbox: (v as any)?.bbox, pageNum: (v as any)?.page_number })))

        const newHighlights: Highlight[] = []

        Object.entries(currentData).forEach(([key, item]: [string, any]) => {
            // Check if item has bbox info (from refiner)
            if (item && typeof item === 'object' && item.bbox) {
                let x1 = 0, y1 = 0, x2 = 0, y2 = 0
                let validBBox = false

                if (Array.isArray(item.bbox)) {
                    const points = item.bbox
                    if (points.length >= 4) {
                        if (points.length === 4) {
                            // [x1, y1, x2, y2]
                            // Verify if it's [x,y,w,h] or [x1,y1,x2,y2]. 
                            // Usually NormalizedBBox is [x1,y1,x2,y2].
                            // If x2 < x1, maybe it's w,h?
                            // Let's assume standard [x1, y1, x2, y2] as per backend extraction_service
                            x1 = points[0]; y1 = points[1]; x2 = points[2]; y2 = points[3];
                        } else {
                            // Polygon (8+ points)
                            const xs = points.filter((_: number, i: number) => i % 2 === 0)
                            const ys = points.filter((_: number, i: number) => i % 2 === 1)
                            if (xs.length > 0) {
                                x1 = Math.min(...xs); x2 = Math.max(...xs)
                                y1 = Math.min(...ys); y2 = Math.max(...ys)
                            }
                        }
                        validBBox = true
                    }
                } else if (typeof item.bbox === 'object') {
                    // Handle Dict format: {x1, y1, x2, y2} or {x, y, w, h}
                    // Prioritize x1/x2 over x/w
                    const b = item.bbox
                    x1 = Number(b.x1 ?? b.x ?? 0)
                    y1 = Number(b.y1 ?? b.y ?? 0)
                    // If x2 is present, use it. If not, try x+w.
                    x2 = b.x2 !== undefined ? Number(b.x2) : (Number(b.w ?? 0) + x1)
                    y2 = b.y2 !== undefined ? Number(b.y2) : (Number(b.h ?? 0) + y1)

                    if (x2 > x1 || y2 > y1) validBBox = true
                }

                if (validBBox) {
                    newHighlights.push({
                        fieldKey: key,
                        content: item.source_text || String(item.value || ''),
                        pageIndex: (item.page_number || item.page || 1) - 1,
                        position: {
                            boundingRect: {
                                x1, y1, x2, y2,
                                width: x2 - x1,
                                height: y2 - y1
                            }
                        }
                    })
                }
            }
        })

        devLog('[Highlights] Generated:', newHighlights.length, 'highlights')
        setHighlights(newHighlights)

    }, [previewData, selectedSubDocIndex])

    // Polling Reference
    const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Polling Logic
    const startPolling = useCallback((jobId: string) => {
        if (pollingRef.current) clearInterval(pollingRef.current)

        const poll = async () => {
            try {
                // Fix import path here if needed, generic usage is fine
                const res = await apiClient.get<any>(`/extraction/job/${jobId}`)
                const job = res.data

                if (isSuccessStatus(job.status) || job.status === 'completed' || job.status === 'confirmed') {
                    if (pollingRef.current) clearInterval(pollingRef.current)

                    // If we have a result, use it
                    if (job.result) {
                        setResult(job.result)
                    }

                    // Update URLs if present in job (important for candidate file)
                    if (job.file_url) setFileUrl(job.file_url)
                    if (job.candidate_file_urls) setCandidateFileUrls(job.candidate_file_urls) // Expecting array from backend now

                    // If we have preview data (standard flow), use it
                    // Always inject debug_data if available
                    // This ensures users can see raw OCR/LLM response even if extraction failed
                    const basePreviewData = job.preview_data || { guide_extracted: {}, other_data: [] }

                    setPreviewData({
                        ...basePreviewData,
                        debug_data: job.debug_data, // Inject debug_data ALWAYS
                        model_fields: basePreviewData.model_fields || model?.fields?.map(f => ({ key: f.key, label: f.label })) || []
                    })

                    setStatus(isSuccessStatus(job.status) ? EXTRACTION_STATUS.PREVIEW_READY : EXTRACTION_STATUS.SUCCESS)

                    // Auto-advance to review step if not there
                    setActiveStep(current => current === 'upload' ? 'review' : current)

                } else if (job.status === 'failed') {
                    if (pollingRef.current) clearInterval(pollingRef.current)
                    setStatus(EXTRACTION_STATUS.ERROR)
                    setError(job.error_message || '추출 실패')
                }
            } catch (err) {
                console.error('Polling error:', err)
            }
        }

        // Initial call
        poll()
        // Interval
        pollingRef.current = setInterval(poll, POLLING_INTERVAL_MS || 2000)
    }, [model?.fields])

    // File processing
    const processFile = useCallback(async (selectedFile: File, selectedCandidateFiles?: File[]) => {
        // Clear any existing polling first
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }

        setFile(selectedFile)
        setCandidateFiles(selectedCandidateFiles || null)
        setFilename(selectedFile.name)
        setStatus(EXTRACTION_STATUS.UPLOADING)
        setError(null)
        setResult(null)
        setCurrentLogId(null)
        setCurrentJobId(null)

        const formData = new FormData()
        formData.append('file', selectedFile)

        // Append multiple candidate files
        if (selectedCandidateFiles && selectedCandidateFiles.length > 0) {
            selectedCandidateFiles.forEach(file => {
                formData.append('candidate_files', file)
            })
        }

        formData.append('model_id', modelId)

        try {
            const res = await apiClient.post('/extraction/start-job', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            })

            const { job_id, file_url, candidate_file_urls, log_id } = res.data
            setCurrentJobId(job_id)
            setFileUrl(file_url)
            if (candidate_file_urls) setCandidateFileUrls(candidate_file_urls)
            if (log_id) setCurrentLogId(log_id)  // Enable retry functionality
            setStatus(EXTRACTION_STATUS.REFINING)

            // Start polling for job status updates
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
                log_id: currentLogId,
                debug_data: previewData?.debug_data // Pass debug data for persistence
            }

            const res = await apiClient.post('/extraction/save-extraction', payload)
            return res.data
        },
        onSuccess: (data) => {
            setResult(data.extracted_data)
            devLog('[AutoSave] Historical log updated successfully')
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
            devLog('[AutoSave] Saved successfully')
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
            devLog('[AutoSave] Skipped - no active job and no log ID')
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
        devLog('[resumeJob] Resuming job:', jobId)
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
        devLog('[loadFromHistory] Loading log:', { id: log.id, file_url: log.file_url, filename: log.filename })
        setResult(log.extracted_data || null)
        setStatus(isSuccessStatus(log.status) ? EXTRACTION_STATUS.COMPLETE : EXTRACTION_STATUS.ERROR)
        setFileUrl(log.file_url || null)
        setFile(null) // No file object when loading from history
        setFilename(log.filename)
        setCurrentLogId(log.id)


        // Use saved preview_data if available (preserves other_data structure)
        // Otherwise fall back to reconstructing from extracted_data
        devLog('[loadFromHistory] preview_data:', JSON.stringify(log.preview_data, null, 2)?.slice(0, 500))
        devLog('[loadFromHistory] extracted_data:', JSON.stringify(log.extracted_data, null, 2)?.slice(0, 500))
        if (log.preview_data) {
            setPreviewData({
                ...log.preview_data,
                debug_data: log.debug_data, // Inject debug data from log level
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
        candidateFiles, setCandidateFiles,
        fileUrl, setFileUrl,
        candidateFileUrls, setCandidateFileUrls,
        candidateFileUrl: candidateFileUrls?.[0] || null,
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
