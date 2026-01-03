import { useState, useCallback, useEffect } from 'react'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { API_CONFIG } from '../constants'

const API_BASE = API_CONFIG.BASE_URL

export interface HistoryItem {
    id: string
    filename: string
    timestamp: number
    modelName: string
    modelId: string
    fileUrl: string
    extractedData: any
}

export interface ExtractedData {
    structured_data?: Record<string, any>
    extracted_text?: string
}

export type ProcessingStage = 'idle' | 'uploading' | 'ocr' | 'llm' | 'complete' | 'error'

interface UseDocumentAnalysisReturn {
    analysisData: ExtractedData | null
    currentFileUrl: string | undefined
    currentFile: File | null
    currentModelId: string | null
    isRetrying: boolean
    processingStage: ProcessingStage
    ocrText: string | undefined
    processingError: string | undefined
    history: HistoryItem[]
    selectedHistoryId: string | null
    handleAnalysisComplete: (data: ExtractedData, fileUrl?: string, filename?: string, file?: File, modelId?: string) => void
    handleSelectHistory: (item: HistoryItem) => void
    handleDeleteHistory: (id: string) => void
    handleRetry: () => Promise<void>
    setCurrentModelId: (id: string | null) => void
}

export function useDocumentAnalysis(getModelName: (id: string) => string): UseDocumentAnalysisReturn {
    const { i18n } = useTranslation()

    const [analysisData, setAnalysisData] = useState<ExtractedData | null>(null)
    const [currentFileUrl, setCurrentFileUrl] = useState<string | undefined>()
    const [currentFile, setCurrentFile] = useState<File | null>(null)
    const [currentModelId, setCurrentModelId] = useState<string | null>(null)
    const [isRetrying, setIsRetrying] = useState(false)

    const [processingStage, setProcessingStage] = useState<ProcessingStage>('idle')
    const [ocrText, _setOcrText] = useState<string | undefined>()
    const [processingError, setProcessingError] = useState<string | undefined>()

    const [history, setHistory] = useState<HistoryItem[]>([])
    const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null)

    // Load history from localStorage
    useEffect(() => {
        const saved = localStorage.getItem('daom_history')
        if (saved) {
            try {
                setHistory(JSON.parse(saved))
            } catch (e) {
                console.error('Failed to load history:', e)
            }
        }
    }, [])

    const handleAnalysisComplete = useCallback((
        data: ExtractedData,
        fileUrl?: string,
        filename?: string,
        file?: File,
        modelId?: string
    ) => {
        setAnalysisData(data)
        setCurrentFileUrl(fileUrl)
        if (file) setCurrentFile(file)
        if (modelId) setCurrentModelId(modelId)
        setProcessingStage('complete')
        setProcessingError(undefined)

        // Add to history
        const modelName = modelId ? getModelName(modelId) : 'Default'
        const newItem: HistoryItem = {
            id: Date.now().toString(),
            filename: filename || 'Document',
            timestamp: Date.now(),
            modelName,
            modelId: modelId || '',
            fileUrl: fileUrl || '',
            extractedData: data.structured_data
        }
        const updatedHistory = [newItem, ...history].slice(0, 50) // Keep last 50
        setHistory(updatedHistory)
        setSelectedHistoryId(newItem.id)
        localStorage.setItem('daom_history', JSON.stringify(updatedHistory))
    }, [history, getModelName])

    const handleSelectHistory = useCallback((item: HistoryItem) => {
        setSelectedHistoryId(item.id)
        setCurrentFileUrl(item.fileUrl)
        setAnalysisData({ structured_data: item.extractedData })
        setCurrentFile(null)
        setCurrentModelId(item.modelId || null)
    }, [])

    const handleDeleteHistory = useCallback((id: string) => {
        const updatedHistory = history.filter(h => h.id !== id)
        setHistory(updatedHistory)
        localStorage.setItem('daom_history', JSON.stringify(updatedHistory))
        if (selectedHistoryId === id) {
            setSelectedHistoryId(null)
            setCurrentFileUrl(undefined)
            setAnalysisData(null)
        }
    }, [history, selectedHistoryId])

    const handleRetry = useCallback(async () => {
        if (!currentFile && !currentFileUrl) {
            toast.error('재처리할 문서가 없습니다')
            return
        }

        setIsRetrying(true)
        const toastId = toast.loading('재처리 중...')

        try {
            let fileUrl = currentFileUrl

            if (currentFile) {
                const formData = new FormData()
                formData.append('file', currentFile)
                const uploadRes = await axios.post(`${API_BASE}/documents/upload`, formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                })
                fileUrl = uploadRes.data.url
            }

            const analyzeRes = await axios.post(`${API_BASE}/documents/analyze`, {
                file_url: fileUrl,
                language: i18n.language,
                model_id: currentModelId || null
            })

            const filename = currentFile?.name || 'Document'
            handleAnalysisComplete(analyzeRes.data, fileUrl, filename, currentFile || undefined, currentModelId || undefined)
            toast.success('재처리 완료!', { id: toastId })
        } catch (error) {
            console.error('Retry error:', error)
            toast.error('재처리 실패', { id: toastId })
        } finally {
            setIsRetrying(false)
        }
    }, [currentFile, currentFileUrl, currentModelId, i18n.language, handleAnalysisComplete])

    return {
        analysisData,
        currentFileUrl,
        currentFile,
        currentModelId,
        isRetrying,
        processingStage,
        ocrText,
        processingError,
        history,
        selectedHistoryId,
        handleAnalysisComplete,
        handleSelectHistory,
        handleDeleteHistory,
        handleRetry,
        setCurrentModelId
    }
}
