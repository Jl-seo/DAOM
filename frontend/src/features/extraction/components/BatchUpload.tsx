/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useCallback, useRef } from 'react'
import { CloudUpload, FileText, X, Play, Pause, Download, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import axios from 'axios'
import { API_CONFIG } from '../../../constants'
import { downloadAsExcel } from '../../../utils/excel'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const API_BASE = API_CONFIG.BASE_URL

interface BatchFile {
    id: string
    file: File
    status: 'pending' | 'uploading' | 'processing' | 'complete' | 'error'
    progress: number
    result?: Record<string, any>
    error?: string
}

interface BatchUploadProps {
    modelId?: string
}

export function BatchUpload({ modelId }: BatchUploadProps) {
    const [files, setFiles] = useState<BatchFile[]>([])
    const [isProcessing, setIsProcessing] = useState(false)
    const [isDragging, setIsDragging] = useState(false)
    const [selectedModelId, setSelectedModelId] = useState(modelId || '')
    const [models, setModels] = useState<any[]>([])
    const fileInputRef = useRef<HTMLInputElement>(null)
    const abortControllerRef = useRef<AbortController | null>(null)

    // Load models on mount
    useState(() => {
        axios.get(`${API_BASE}/models`).then(res => setModels(res.data)).catch(() => { })
    })

    const addFiles = useCallback((newFiles: FileList | File[]) => {
        const validFiles = Array.from(newFiles).filter(f =>
            /\.(pdf|jpg|jpeg|png)$/i.test(f.name)
        )

        const batchFiles: BatchFile[] = validFiles.map(file => ({
            id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
            file,
            status: 'pending',
            progress: 0
        }))

        setFiles(prev => [...prev, ...batchFiles])
    }, [])

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        addFiles(e.dataTransfer.files)
    }, [addFiles])

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
    }, [])

    const removeFile = useCallback((id: string) => {
        setFiles(prev => prev.filter(f => f.id !== id))
    }, [])

    const clearCompleted = useCallback(() => {
        setFiles(prev => prev.filter(f => f.status !== 'complete'))
    }, [])

    const processFiles = useCallback(async () => {
        const pendingFiles = files.filter(f => f.status === 'pending' || f.status === 'error')
        if (pendingFiles.length === 0) return

        setIsProcessing(true)
        abortControllerRef.current = new AbortController()

        for (const batchFile of pendingFiles) {
            if (abortControllerRef.current?.signal.aborted) break

            try {
                // Update status to uploading
                setFiles(prev => prev.map(f =>
                    f.id === batchFile.id ? { ...f, status: 'uploading', progress: 20 } : f
                ))

                // Upload file
                const formData = new FormData()
                formData.append('file', batchFile.file)
                const uploadRes = await axios.post(`${API_BASE}/documents/upload`, formData)
                const fileUrl = uploadRes.data.url

                // Update status to processing
                setFiles(prev => prev.map(f =>
                    f.id === batchFile.id ? { ...f, status: 'processing', progress: 60 } : f
                ))

                // Process document
                const analyzeRes = await axios.post(`${API_BASE}/documents/analyze`, {
                    file_url: fileUrl,
                    language: 'ko',
                    model_id: selectedModelId || null
                })

                // Update with result
                setFiles(prev => prev.map(f =>
                    f.id === batchFile.id ? {
                        ...f,
                        status: 'complete',
                        progress: 100,
                        result: analyzeRes.data.structured_data
                    } : f
                ))

            } catch (error: any) {
                setFiles(prev => prev.map(f =>
                    f.id === batchFile.id ? {
                        ...f,
                        status: 'error',
                        progress: 0,
                        error: error.message || '처리 실패'
                    } : f
                ))
            }
        }

        setIsProcessing(false)
    }, [files, selectedModelId])

    const stopProcessing = useCallback(() => {
        abortControllerRef.current?.abort()
        setIsProcessing(false)
    }, [])

    const downloadAllAsExcel = useCallback(() => {
        const completedFiles = files.filter(f => f.status === 'complete' && f.result)
        if (completedFiles.length === 0) {
            toast.error('다운로드할 데이터가 없습니다')
            return
        }

        // Combine all results into one array
        const allData = completedFiles.map(f => ({
            파일명: f.file.name,
            ...Object.fromEntries(
                Object.entries(f.result!).map(([key, value]) => [
                    key,
                    typeof value === 'object' && value?.value ? value.value : value
                ])
            )
        }))

        downloadAsExcel(allData, `batch_export_${completedFiles.length}files`)
        toast.success(`${completedFiles.length}개 파일 다운로드 완료!`)
    }, [files])

    const completedCount = files.filter(f => f.status === 'complete').length
    const errorCount = files.filter(f => f.status === 'error').length
    const pendingCount = files.filter(f => f.status === 'pending').length

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-foreground">배치 처리</h2>
                    <p className="text-muted-foreground">여러 문서를 한 번에 처리하고 통합 Excel로 다운로드</p>
                </div>
                <select
                    value={selectedModelId}
                    onChange={(e) => setSelectedModelId(e.target.value)}
                    className="px-4 py-2 border border-border rounded-lg bg-background"
                    disabled={isProcessing}
                >
                    <option value="">기본 모델</option>
                    {models.map(m => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                </select>
            </div>

            {/* Drop Zone */}
            <div
                className={clsx(
                    "border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer",
                    isDragging
                        ? "border-primary bg-primary/5 scale-[1.01]"
                        : "border-border hover:border-primary bg-muted/50"
                )}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(e) => e.target.files && addFiles(e.target.files)}
                    className="hidden"
                />
                <div className="flex flex-col items-center gap-3">
                    <div className={clsx(
                        "p-4 rounded-2xl transition-colors",
                        isDragging ? "bg-primary/10" : "bg-card shadow-lg"
                    )}>
                        <CloudUpload className={clsx(
                            "w-10 h-10 transition-colors",
                            isDragging ? "text-primary" : "text-muted-foreground"
                        )} />
                    </div>
                    <div>
                        <p className="text-lg font-semibold text-foreground">
                            {isDragging ? "여기에 놓으세요!" : "파일을 드래그하거나 클릭하세요"}
                        </p>
                        <p className="text-sm text-muted-foreground">PDF, JPG, PNG • 여러 파일 선택 가능</p>
                    </div>
                </div>
            </div>

            {/* File Queue */}
            {files.length > 0 && (
                <Card className="overflow-hidden">
                    {/* Queue Header */}
                    <div className="px-4 py-3 bg-muted border-b border-border flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <span className="font-semibold text-foreground">
                                대기열 ({files.length}개)
                            </span>
                            <div className="flex items-center gap-2 text-sm">
                                {completedCount > 0 && (
                                    <span className="text-chart-2">✓ {completedCount} 완료</span>
                                )}
                                {errorCount > 0 && (
                                    <span className="text-destructive">✗ {errorCount} 오류</span>
                                )}
                                {pendingCount > 0 && (
                                    <span className="text-muted-foreground">◷ {pendingCount} 대기</span>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {completedCount > 0 && (
                                <Button variant="ghost" size="sm" onClick={clearCompleted}>
                                    완료 항목 삭제
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* File List */}
                    <div className="max-h-[300px] overflow-y-auto divide-y divide-border">
                        {files.map((batchFile) => (
                            <div key={batchFile.id} className="px-4 py-3 flex items-center gap-4 hover:bg-accent">
                                <div className={clsx(
                                    "p-2 rounded-lg",
                                    batchFile.status === 'complete' ? "bg-chart-2/10" :
                                        batchFile.status === 'error' ? "bg-destructive/10" :
                                            "bg-muted"
                                )}>
                                    <FileText className={clsx(
                                        "w-5 h-5",
                                        batchFile.status === 'complete' ? "text-chart-2" :
                                            batchFile.status === 'error' ? "text-destructive" :
                                                "text-muted-foreground"
                                    )} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="font-medium text-foreground truncate">{batchFile.file.name}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {(batchFile.file.size / 1024).toFixed(1)} KB
                                    </p>
                                </div>
                                <div className="flex items-center gap-3">
                                    {batchFile.status === 'pending' && (
                                        <span className="text-sm text-muted-foreground">대기 중</span>
                                    )}
                                    {(batchFile.status === 'uploading' || batchFile.status === 'processing') && (
                                        <div className="flex items-center gap-2">
                                            <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                            <span className="text-sm text-primary">
                                                {batchFile.status === 'uploading' ? '업로드 중' : '분석 중'}
                                            </span>
                                        </div>
                                    )}
                                    {batchFile.status === 'complete' && (
                                        <CheckCircle className="w-5 h-5 text-chart-2" />
                                    )}
                                    {batchFile.status === 'error' && (
                                        <div className="flex items-center gap-2">
                                            <XCircle className="w-5 h-5 text-destructive" />
                                            <span className="text-xs text-destructive">{batchFile.error}</span>
                                        </div>
                                    )}
                                    {batchFile.status === 'pending' && !isProcessing && (
                                        <button
                                            onClick={() => removeFile(batchFile.id)}
                                            className="p-1 hover:bg-accent rounded"
                                        >
                                            <X className="w-4 h-4 text-muted-foreground" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Actions */}
                    <div className="px-4 py-3 bg-muted border-t border-border flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            {!isProcessing ? (
                                <Button
                                    onClick={processFiles}
                                    disabled={pendingCount === 0 && errorCount === 0}
                                >
                                    <Play className="w-4 h-4 mr-2" />
                                    처리 시작 ({pendingCount + errorCount}개)
                                </Button>
                            ) : (
                                <Button variant="destructive" onClick={stopProcessing}>
                                    <Pause className="w-4 h-4 mr-2" />
                                    중지
                                </Button>
                            )}
                        </div>
                        <Button
                            variant="secondary"
                            onClick={downloadAllAsExcel}
                            disabled={completedCount === 0}
                            className="bg-chart-2 hover:bg-chart-2/90 text-primary-foreground"
                        >
                            <Download className="w-4 h-4 mr-2" />
                            통합 Excel 다운로드 ({completedCount}개)
                        </Button>
                    </div>
                </Card>
            )}
        </div>
    )
}
