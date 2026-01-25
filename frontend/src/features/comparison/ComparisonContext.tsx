import { createContext, useContext, useState, useRef, type ReactNode, useCallback, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api'
import { isSuccessStatus } from '../verification/constants/status'
import type { ExtractionLog, PreviewData, ExtractionModel } from '../verification/types'

// Development-only logging helper
const devLog = (...args: any[]) => {
    if (import.meta.env.DEV) {
        console.log('[ComparisonContext]', ...args)
    }
}

const POLLING_INTERVAL_MS = 2000

// ==========================================
// TYPES
// ==========================================

export interface ComparisonResult {
    differences: Difference[]
    error?: string
    metadata?: {
        model?: string
        method?: string
        rules_applied?: boolean
        pixel_diff_count?: number
    }
}

export interface Difference {
    id: string | number
    description: string
    category: string
    location_1: number[] | null // [ymin, xmin, ymax, xmax] 0-1000
    location_2: number[] | null
    page_number?: number
    confidence?: number
}

export interface ComparisonData {
    candidate_index: number
    result: ComparisonResult
    file_url?: string
    filename?: string
    error?: string
}

// ==========================================
// CONTEXT
// ==========================================

interface ComparisonContextValue {
    // Model
    model: ExtractionModel | null
    setModel: (model: ExtractionModel | null) => void

    // Status
    status: 'idle' | 'uploading' | 'processing' | 'refining' | 'complete' | 'error'
    setStatus: (status: ComparisonContextValue['status']) => void
    isRefining: boolean

    // Files
    baselineFile: File | null
    baselineFileUrl: string | null
    candidateFiles: File[] | null
    candidateFileUrls: string[] | null
    setBaselineFile: (file: File | null) => void
    setBaselineFileUrl: (url: string | null) => void
    setCandidateFiles: (files: File[] | null) => void
    setCandidateFileUrls: (urls: string[] | null) => void

    // Results
    comparisonResult: ComparisonResult | null
    comparisons: ComparisonData[] | null
    previewData: PreviewData | null
    setComparisonResult: (result: ComparisonResult | null) => void
    setComparisons: (comparisons: ComparisonData[] | null) => void
    setPreviewData: (data: PreviewData | null) => void

    // Job/Log tracking
    currentJobId: string | null
    currentLogId: string | null
    setCurrentJobId: (id: string | null) => void
    setCurrentLogId: (id: string | null) => void

    // Actions
    processComparison: (baselineFile: File, candidateFiles: File[]) => Promise<void>
    handleRetry: () => void
    handleReset: () => void
    loadFromHistory: (log: ExtractionLog) => void
}

const ComparisonContext = createContext<ComparisonContextValue | null>(null)

export function useComparison() {
    const context = useContext(ComparisonContext)
    if (!context) {
        throw new Error('useComparison must be used within ComparisonProvider')
    }
    return context
}

// ==========================================
// PROVIDER
// ==========================================

interface ComparisonProviderProps {
    children: ReactNode
    modelId?: string
}

export function ComparisonProvider({ children, modelId }: ComparisonProviderProps) {
    // Model
    const [model, setModel] = useState<ExtractionModel | null>(null)

    // Status
    const [status, setStatus] = useState<ComparisonContextValue['status']>('idle')

    // Files
    const [baselineFile, setBaselineFile] = useState<File | null>(null)
    const [baselineFileUrl, setBaselineFileUrl] = useState<string | null>(null)
    const [candidateFiles, setCandidateFiles] = useState<File[] | null>(null)
    const [candidateFileUrls, setCandidateFileUrls] = useState<string[] | null>(null)

    // Results
    const [comparisonResult, setComparisonResult] = useState<ComparisonResult | null>(null)
    const [comparisons, setComparisons] = useState<ComparisonData[] | null>(null)
    const [previewData, setPreviewData] = useState<PreviewData | null>(null)

    // Job/Log tracking
    const [currentJobId, setCurrentJobId] = useState<string | null>(null)
    const [currentLogId, setCurrentLogId] = useState<string | null>(null)

    // Polling reference
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

    // Derived state
    const isRefining = status === 'refining' || status === 'processing'

    // Polling logic
    const startPolling = useCallback((jobId: string) => {
        if (pollingRef.current) clearInterval(pollingRef.current)

        const poll = async () => {
            try {
                const res = await apiClient.get<any>(`/extraction/job/${jobId}`)
                const job = res.data

                devLog('Poll result:', job.status)

                if (isSuccessStatus(job.status) || job.status === 'completed' || job.status === 'confirmed') {
                    if (pollingRef.current) clearInterval(pollingRef.current)

                    // Update URLs
                    if (job.file_url) setBaselineFileUrl(job.file_url)
                    if (job.candidate_file_urls && job.candidate_file_urls.length > 0) {
                        setCandidateFileUrls(job.candidate_file_urls)
                    }

                    // Update preview data with comparison results
                    if (job.preview_data) {
                        setPreviewData(job.preview_data)
                        if (job.preview_data.comparison_result) {
                            setComparisonResult(job.preview_data.comparison_result)
                        }
                        if (job.preview_data.comparisons) {
                            setComparisons(job.preview_data.comparisons)
                        }
                    }

                    setStatus('complete')
                    toast.success('비교 완료')
                } else if (job.status === 'failed') {
                    if (pollingRef.current) clearInterval(pollingRef.current)
                    setStatus('error')
                    toast.error(job.error_message || '비교 실패')
                }
            } catch (err) {
                console.error('Polling error:', err)
            }
        }

        poll()
        pollingRef.current = setInterval(poll, POLLING_INTERVAL_MS)
    }, [])

    // Process comparison
    const processComparison = useCallback(async (baseline: File, candidates: File[]) => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }

        setBaselineFile(baseline)
        setCandidateFiles(candidates)
        setStatus('uploading')

        const formData = new FormData()
        formData.append('file', baseline)
        candidates.forEach(f => formData.append('candidate_files', f))
        if (modelId) formData.append('model_id', modelId)

        try {
            const res = await apiClient.post('/extraction/process', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            })

            const { job_id, file_url, candidate_file_urls, log_id } = res.data

            setCurrentJobId(job_id)
            if (log_id) setCurrentLogId(log_id)
            if (file_url) setBaselineFileUrl(file_url)
            if (candidate_file_urls) setCandidateFileUrls(candidate_file_urls)

            setStatus('processing')
            startPolling(job_id)
            toast.info('비교 분석을 시작합니다...')
        } catch (error: any) {
            setStatus('error')
            toast.error('업로드 실패: ' + (error?.message || '알 수 없는 오류'))
        }
    }, [modelId, startPolling])

    // Retry mutation
    const retryMutation = useMutation({
        mutationFn: async () => {
            if (!currentLogId) throw new Error('No log to retry')
            const res = await apiClient.post(`/extraction/retry/${currentLogId}`)
            return res.data
        },
        onSuccess: (data) => {
            setCurrentJobId(data.job_id)
            if (data.file_url) setBaselineFileUrl(data.file_url)
            // Preserve existing candidate URLs if backend doesn't return new ones
            if (data.candidate_file_urls && data.candidate_file_urls.length > 0) {
                setCandidateFileUrls(data.candidate_file_urls)
            }
            setStatus('refining')
            startPolling(data.job_id)
            toast.info('재비교를 시작합니다...')
        },
        onError: (error: any) => {
            toast.error(`재시도 실패: ${error?.message || '알 수 없는 오류'}`)
        }
    })

    const handleRetry = useCallback(() => {
        if (currentLogId) {
            retryMutation.mutate()
        } else if (baselineFile && candidateFiles) {
            processComparison(baselineFile, candidateFiles)
        } else {
            toast.error('재시도할 수 없습니다.')
        }
    }, [currentLogId, baselineFile, candidateFiles, retryMutation, processComparison])

    const handleReset = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
        }
        setBaselineFile(null)
        setBaselineFileUrl(null)
        setCandidateFiles(null)
        setCandidateFileUrls(null)
        setComparisonResult(null)
        setComparisons(null)
        setPreviewData(null)
        setCurrentJobId(null)
        setCurrentLogId(null)
        setStatus('idle')
    }, [])

    const loadFromHistory = useCallback((log: ExtractionLog) => {
        devLog('Loading from history:', log.id)

        setBaselineFileUrl(log.file_url || null)
        setCandidateFileUrls(log.candidate_file_urls || null)
        setCurrentLogId(log.id)

        if (log.preview_data) {
            setPreviewData(log.preview_data)
            if (log.preview_data.comparison_result) {
                setComparisonResult(log.preview_data.comparison_result)
            }
            if (log.preview_data.comparisons) {
                setComparisons(log.preview_data.comparisons)
            }
        }

        setStatus(isSuccessStatus(log.status) ? 'complete' : 'error')
    }, [])

    const value: ComparisonContextValue = useMemo(() => ({
        model, setModel,
        status, setStatus,
        isRefining,
        baselineFile, baselineFileUrl,
        candidateFiles, candidateFileUrls,
        setBaselineFile, setBaselineFileUrl,
        setCandidateFiles, setCandidateFileUrls,
        comparisonResult, comparisons, previewData,
        setComparisonResult, setComparisons, setPreviewData,
        currentJobId, currentLogId,
        setCurrentJobId, setCurrentLogId,
        processComparison, handleRetry, handleReset, loadFromHistory
    }), [
        model, status, isRefining,
        baselineFile, baselineFileUrl, candidateFiles, candidateFileUrls,
        comparisonResult, comparisons, previewData,
        currentJobId, currentLogId,
        processComparison, handleRetry, handleReset, loadFromHistory
    ])

    return (
        <ComparisonContext.Provider value={value}>
            {children}
        </ComparisonContext.Provider>
    )
}
