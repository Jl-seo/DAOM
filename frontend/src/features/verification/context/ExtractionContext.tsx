/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable react-hooks/exhaustive-deps */

/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useRef, type ReactNode, useCallback, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { POLLING_INTERVAL_MS, MAX_POLLING_ATTEMPTS } from '../constants'

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
    files: File[] | null // Multi-file support
    setFiles: (files: File[] | null) => void
    candidateFiles: File[] | null // NEW: Array
    setCandidateFiles: (files: File[] | null) => void
    fileUrl: string | null
    fileUrls: string[] | null // Multi-file URLs
    setFileUrls: (urls: string[] | null) => void
    candidateFileUrls?: string[] | null // NEW: Array
    setCandidateFileUrls: (urls: string[] | null) => void
    candidateFileUrl: string | null // Legacy/Convenience: First candidate URL
    setFileUrl: (url: string | null) => void
    isDragging: boolean
    setIsDragging: (dragging: boolean) => void
    filename: string | null
    setFilename: (name: string | null) => void
    filenames: string[] | null // Multi-file names
    setFilenames: (names: string[] | null) => void

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
    processFile: (file: File | File[], candidateFiles?: File[]) => Promise<void>
    handleConfirmSelection: (selectedColumns: string[], editedGuideData?: Record<string, any>, editedOtherData?: any[]) => void
    handleRetry: () => void
    handleReset: () => void
    handleCancelPreview: () => void
    loadFromHistory: (log: ExtractionLog) => void
    resumeJob: (jobId: string, fileUrl?: string, status?: ExtractionStatus, logId?: string) => void // New: Resume in-progress job
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
    initialJobId?: string
    initialLogId?: string
    children: ReactNode
}

export function ExtractionProvider({ modelId, initialJobId, initialLogId, children }: ExtractionProviderProps) {
    const navigate = useNavigate()
    // Model state
    const [model, setModel] = useState<ExtractionModel | null>(null)

    // Navigation
    const [activeStep, setActiveStep] = useState<ViewStep>('history')

    // Status
    const [status, setStatus] = useState<ExtractionStatus>('idle')

    // File
    const [file, setFile] = useState<File | null>(null)
    const [files, setFiles] = useState<File[] | null>(null) // NEW
    const [candidateFiles, setCandidateFiles] = useState<File[] | null>(null)
    const [fileUrl, setFileUrl] = useState<string | null>(null)
    const [fileUrls, setFileUrls] = useState<string[] | null>(null) // NEW
    const [candidateFileUrls, setCandidateFileUrls] = useState<string[] | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [filename, setFilename] = useState<string | null>(null)
    const [filenames, setFilenames] = useState<string[] | null>(null) // NEW

    // State for Job & Log tracking
    const [currentJobId, setCurrentJobId] = useState<string | null>(null)
    const [currentLogId, setCurrentLogId] = useState<string | null>(null)

    // Preview & Result Data
    const [previewData, setPreviewData] = useState<PreviewData | null>(null)
    const [selectedSubDocIndex, setSelectedSubDocIndex] = useState(0)
    const [result, setResult] = useState<Record<string, any> | null>(null)

    // UI State
    const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)

    // Load job from URL if initialJobId is present
    useEffect(() => {
        if (initialJobId && initialJobId !== currentJobId) {
            // Load job data from API
            apiClient.get(`/extraction/job/${initialJobId}`)
                .then(res => {
                    const { status: jobStatus, extracted_data, preview_data } = res.data
                    setCurrentJobId(initialJobId)

                    // Check for S100 (SUCCESS) or legacy 'completed'
                    const isSuccess = (jobStatus === EXTRACTION_STATUS.SUCCESS || jobStatus === 'completed' || jobStatus === 'preview_ready' || jobStatus === EXTRACTION_STATUS.PREVIEW_READY)
                    if (isSuccess) {
                        setStatus(EXTRACTION_STATUS.PREVIEW_READY)
                        setResult(extracted_data || null)
                        if (preview_data) {
                            setPreviewData({
                                ...preview_data,
                                model_fields: preview_data?.model_fields || model?.fields?.map((f: any) => ({ key: f.key, label: f.label })) || []
                            })
                        }
                        setActiveStep('review')
                    } else if (jobStatus === EXTRACTION_STATUS.ANALYZING || jobStatus === EXTRACTION_STATUS.REFINING ||
                        jobStatus === 'processing' || jobStatus === 'analyzing') {
                        setStatus(EXTRACTION_STATUS.ANALYZING)
                        setActiveStep('upload')
                        startPolling(initialJobId)
                    }
                })
                .catch(err => {
                    console.error('Failed to load job from URL:', err)
                    // Fallback to history view
                    setActiveStep('history')
                })
        }
    }, [initialJobId, model])

    // Load extraction log from URL if initialLogId is present (deep-link)
    useEffect(() => {
        if (initialLogId && initialLogId !== currentLogId && model) {
            devLog('[DeepLink] Loading log by ID:', initialLogId)
            apiClient.get(`/extraction/log/${initialLogId}`)
                .then(res => {
                    const logData = res.data
                    devLog('[DeepLink] Log loaded:', { id: logData.id, filename: logData.filename })
                    // Reuse loadFromHistory logic by constructing an ExtractionLog-compatible object
                    loadFromHistory(logData as any)
                })
                .catch(err => {
                    console.error('[DeepLink] Failed to load log:', err)
                    toast.error('추출 기록을 불러올 수 없습니다')
                    setActiveStep('history')
                })
        }
    }, [initialLogId, model])

    // Polling ref
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const pollingAttemptRef = useRef(0)

    // Polling function for job status
    const startPolling = useCallback((jobId: string) => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
        }
        pollingAttemptRef.current = 0

        const poll = async () => {
            pollingAttemptRef.current += 1

            // Enforce polling timeout
            if (pollingAttemptRef.current > MAX_POLLING_ATTEMPTS) {
                if (pollingRef.current) {
                    clearInterval(pollingRef.current)
                    pollingRef.current = null
                }
                setStatus(EXTRACTION_STATUS.ERROR)
                setError('추출 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.')
                toast.error('추출 시간 초과')
                return
            }

            try {
                const res = await apiClient.get(`/extraction/job/${jobId}`)
                // Backend returns 'extracted_data' not 'result' — support both for safety
                const { status: jobStatus, result: jobResult, extracted_data, preview_data, error: jobError } = res.data
                const effectiveResult = jobResult || extracted_data

                devLog('[Polling] Status:', jobStatus, 'Preview:', !!preview_data, 'Result:', !!effectiveResult, 'Attempt:', pollingAttemptRef.current)

                // Check for SUCCESS(S100) or legacy 'completed'
                const isSuccess = (jobStatus === EXTRACTION_STATUS.SUCCESS || jobStatus === 'completed' || jobStatus === 'preview_ready' || jobStatus === EXTRACTION_STATUS.PREVIEW_READY)

                if (isSuccess) {
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                        pollingRef.current = null
                    }

                    // 1. First, set intermediate rendering state to let React paint the spinner
                    setStatus((EXTRACTION_STATUS as any).RENDERING)

                    // 2. Wait a tick for the browser to paint the spinner before locking the main thread with massive data (e.g. 6000+ rows)
                    setTimeout(() => {
                        // Force update status to ready
                        setStatus(EXTRACTION_STATUS.PREVIEW_READY)

                        // Update result and preview data
                        setResult(effectiveResult)
                        if (preview_data) {
                            setPreviewData({
                                ...preview_data,
                                // Ensure model fields are populated
                                model_fields: preview_data.model_fields || model?.fields?.map((f: any) => ({ key: f.key, label: f.label })) || []
                            })
                        } else if (res.data.preview_data) {
                            setPreviewData(res.data.preview_data)
                        }

                        // Move to review step
                        setActiveStep('review')
                        toast.success('추출이 완료되었습니다')
                    }, 50)
                } else if (jobStatus === EXTRACTION_STATUS.FAILED || jobStatus === EXTRACTION_STATUS.ERROR || jobError) {
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current)
                        pollingRef.current = null
                    }
                    setStatus(EXTRACTION_STATUS.ERROR)
                    setError(jobError || 'Extraction failed')
                    toast.error('추출 실패: ' + (jobError || 'Unknown error'))
                } else if (jobStatus) {
                    // Update intermediate statuses (e.g. Analyzing, Refining)
                    setStatus(jobStatus as any)
                }
            } catch (e: any) {
                devLog('[Polling] Error:', e)
            }
        }

        poll() // Initial poll
        pollingRef.current = setInterval(poll, POLLING_INTERVAL_MS)
    }, [model?.fields])

    // File processing
    const processFile = useCallback(async (selectedInput: File | File[], selectedCandidateFiles?: File[], barcode?: string) => {
        // Clear any existing polling first
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }

        // Handle single vs key input
        let fileList: File[] = []
        if (Array.isArray(selectedInput)) {
            fileList = selectedInput
        } else {
            fileList = [selectedInput]
        }

        const primaryFile = fileList[0]

        setFile(primaryFile)
        setFiles(fileList)
        setCandidateFiles(selectedCandidateFiles || null)
        setFilename(primaryFile.name)
        setFilenames(fileList.map(f => f.name))

        setStatus(EXTRACTION_STATUS.UPLOADING)
        setError(null)
        setResult(null)
        setCurrentLogId(null)
        setCurrentJobId(null)

        const formData = new FormData()
        // Primary file — backend expects 'file' (singular UploadFile)
        formData.append('file', fileList[0])

        // Append multiple candidate files
        if (selectedCandidateFiles && selectedCandidateFiles.length > 0) {
            selectedCandidateFiles.forEach(file => {
                formData.append('candidate_files', file)
            })
        }

        formData.append('model_id', modelId)

        // Append optional barcode for DEX validation
        if (barcode) {
            formData.append('barcode', barcode)
        }

        try {
            const res = await apiClient.post('/extraction/start-job', formData)

            const { job_id, file_url, candidate_file_urls, log_id } = res.data
            setCurrentJobId(job_id)
            setFileUrl(file_url)
            // If backend returns list of file_urls (it should now, but maybe not in response yet)
            // We might need to fetch job details to get full list if start-job response is legacy compatible
            // But let's assume we can fetch it via polling later.

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

        // 중복 저장 방지
        if (confirmJobMutation.isPending || saveLogMutation.isPending) {
            console.log('[ExtractionContext] Save already in progress, ignoring')
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
        onMutate: () => {
            // 재시도 전 현재 candidateFileUrls 저장
            return { previousCandidateUrls: candidateFileUrls }
        },
        onSuccess: (data, _, context) => {
            setCurrentJobId(data.job_id)
            if (data.file_url) setFileUrl(data.file_url)

            // 재시도 시 후보 파일 URL 유지
            // 백엔드에서 반환하면 업데이트, 없으면 기존 값 유지
            if (data.candidate_file_urls && data.candidate_file_urls.length > 0) {
                setCandidateFileUrls(data.candidate_file_urls)
            } else if (context?.previousCandidateUrls && context.previousCandidateUrls.length > 0) {
                // 백엔드에서 반환하지 않았으면 이전 값 복구
                devLog('[Retry] Preserving previous candidateFileUrls:', context.previousCandidateUrls.length)
            }

            setStatus(EXTRACTION_STATUS.REFINING)

            // 비교 모델은 현재 화면 유지 (로딩 오버레이 표시)
            // 일반 추출 모델은 upload 화면으로 이동 (로딩 상태 표시)
            if (model?.model_type !== 'comparison') {
                setActiveStep('upload')
            }

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
        // 중복 재시도 방지
        if (retryMutation.isPending) {
            console.log('[ExtractionContext] Retry already in progress, ignoring')
            return
        }

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
        // Reset URL back to model page
        navigate(`/models/${modelId}`, { replace: true })
    }, [navigate, modelId])

    const handleCancelPreview = useCallback(() => {
        // Since jobs are asynchronous, we just clear local state and go back to history.
        // The job continues in the background.
        handleReset()
        setActiveStep('history')
    }, [handleReset])

    const resumeJob = useCallback((jobId: string, url?: string, jobStatus?: ExtractionStatus, logId?: string) => {
        devLog('[resumeJob] Resuming job:', jobId)
        setCurrentJobId(jobId)
        if (url) setFileUrl(url)
        if (logId) setCurrentLogId(logId)

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

    const loadFromHistory = useCallback(async (initialLog: ExtractionLog) => {
        devLog('[loadFromHistory] Loading log:', { id: initialLog.id, file_url: initialLog.file_url, filename: initialLog.filename })

        // 1. Set immediate state from list item (optimistic update)
        setStatus(isSuccessStatus(initialLog.status) ? EXTRACTION_STATUS.COMPLETE : EXTRACTION_STATUS.ERROR)
        setFileUrl(initialLog.file_url || null)
        setFile(null)
        setFilename(initialLog.filename)
        setCurrentLogId(initialLog.id)

        // 2. Immediately switch to review/complete view for instant feedback
        setActiveStep('complete')

        navigate(`/models/${modelId}/extractions/${initialLog.id}`, { replace: true })

        // 3. Fetch FULL hydrated log from API to get blob content (enriches the view)
        try {
            const res = await apiClient.get<ExtractionLog>(`/extraction/logs/${initialLog.id}?model_id=${modelId}`)
            const fullLog = res.data
            devLog('[loadFromHistory] Fetched full log:', fullLog.id)

            // Update result with fully hydrated data
            setResult(fullLog.extracted_data || null)

            if (fullLog.candidate_file_urls && fullLog.candidate_file_urls.length > 0) {
                setCandidateFileUrls(fullLog.candidate_file_urls)
            }

            // Robust Restoration Logic using FULL log
            const restorePreviewData = (inputPreview: PreviewData | null | undefined): PreviewData => {
                const base = inputPreview || {
                    guide_extracted: fullLog.extracted_data || {},
                    other_data: [],
                    sub_documents: [],
                    model_fields: model?.fields?.map(f => ({ key: f.key, label: f.label })) || []
                }

                return {
                    ...base,
                    debug_data: fullLog.debug_data,
                    raw_content: base.raw_content || fullLog.extracted_data?.raw_content || fullLog.debug_data?.ocr_result?.content || fullLog.debug_data?.doc_intel_content_preview || "",
                    raw_tables: base.raw_tables || fullLog.extracted_data?.raw_tables || fullLog.debug_data?.ocr_result?.tables || []
                }
            }

            setPreviewData(restorePreviewData(fullLog.preview_data))

        } catch (e) {
            console.error('[loadFromHistory] Failed to fetch full log details:', e)
            // Fallback to initialLog
            const restorePreviewDataFallback = (inputPreview: PreviewData | null | undefined): PreviewData => {
                const base = inputPreview || {
                    guide_extracted: initialLog.extracted_data || {},
                    other_data: [],
                    sub_documents: [],
                    model_fields: model?.fields?.map(f => ({ key: f.key, label: f.label })) || []
                }
                return {
                    ...base,
                    debug_data: initialLog.debug_data,
                    raw_content: base.raw_content || initialLog.extracted_data?.raw_content || "",
                    raw_tables: base.raw_tables || initialLog.extracted_data?.raw_tables || []
                }
            }
            setPreviewData(restorePreviewDataFallback(initialLog.preview_data))
            toast.error("로그 상세 정보를 불러오는데 실패했습니다. 일부 데이터가 누락될 수 있습니다.")
        }
    }, [model?.fields, navigate, modelId])

    // Generate highlights from previewData
    const highlights = useMemo(() => {
        if (!previewData) return []

        const newHighlights: Highlight[] = []

        // Helper to process extracted data recursively
        const processData = (data: any, pageOffset = 0) => {
            if (!data) return

            if (typeof data === 'object') {

                Object.entries(data).forEach(([key, item]: [string, any]) => {
                    if (item && typeof item === 'object' && 'bbox' in item && item.bbox) {
                        const [x1, y1, x2, y2] = item.bbox
                        newHighlights.push({
                            fieldKey: key,
                            content: item.source_text || String(item.value || ''),
                            pageIndex: (item.page_number || item.page || 1) - 1 + pageOffset,
                            fileId: item.file_id, // Propagate file_id
                            position: {
                                boundingRect: {
                                    x1, y1, x2, y2,
                                    width: x2 - x1,
                                    height: y2 - y1
                                }
                            }
                        })
                    } else if (item && typeof item === 'object') {
                        processData(item, pageOffset)
                    }
                })
            }
        }

        // 1. Process guide extracted data
        // Support Legacy vs Sub-documents
        if (previewData.sub_documents && previewData.sub_documents.length > 0) {
            previewData.sub_documents.forEach(doc => {
                if (doc.data?.guide_extracted) {
                    processData(doc.data.guide_extracted)
                }
            })
        } else if (previewData.guide_extracted) {
            // TABLE MODE defense: guide_extracted is an array of flat rows (no bbox typically)
            if (Array.isArray(previewData.guide_extracted)) {
                previewData.guide_extracted.forEach((row: any, rowIdx: number) => {
                    if (row && typeof row === 'object' && 'bbox' in row && row.bbox) {
                        const [x1, y1, x2, y2] = row.bbox
                        newHighlights.push({
                            fieldKey: `table_row_${rowIdx}`,
                            content: row._source_text || '',
                            pageIndex: (row.page_number || 1) - 1,
                            position: {
                                boundingRect: {
                                    x1, y1, x2, y2,
                                    width: x2 - x1,
                                    height: y2 - y1
                                }
                            }
                        })
                    }
                })
            } else {
                processData(previewData.guide_extracted)
            }
        }

        // 2. Process other data (tables/grids) if they have bboxes
        if (previewData.other_data) {
            previewData.other_data.forEach((item: any) => {
                if (item.bbox) {
                    const [x1, y1, x2, y2] = item.bbox
                    newHighlights.push({
                        fieldKey: `other_${item.column}_${item.row || 0}`, // unique derived key
                        content: String(item.value || ''),
                        pageIndex: (item.page_number || 1) - 1,
                        fileId: item.file_id, // Propagate file_id
                        position: {
                            boundingRect: {
                                x1, y1, x2, y2,
                                width: x2 - x1,
                                height: y2 - y1
                            }
                        }
                    })
                }
            })
        }

        return newHighlights
    }, [previewData])

    const value: ExtractionContextValue = useMemo(() => ({
        model, setModel,
        activeStep, setActiveStep,
        status, setStatus,
        file, setFile,
        files, setFiles, // NEW
        candidateFiles, setCandidateFiles,
        fileUrl, setFileUrl, // Primary (First) URL
        fileUrls, setFileUrls, // NEW: All URLs
        candidateFileUrls, setCandidateFileUrls,
        candidateFileUrl: candidateFileUrls?.[0] || null,
        filename, setFilename,
        filenames, setFilenames, // NEW
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
        model, activeStep, status, file, files, fileUrl, fileUrls, filename, filenames, isDragging,
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
