import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Upload, FileText, AlertTriangle, X } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ExtractionStatus } from '../types'
import { isProcessingStatus, isReviewNeededStatus, isSuccessStatus, isErrorStatus, STATUS_LABELS, EXTRACTION_STATUS } from '../constants/status'

interface ExtractionUploadViewProps {
    file: File | null
    status: ExtractionStatus
    error?: string | null
    onFileSelect: (file: File) => void
    onCancel: () => void
}

export function ExtractionUploadView({
    file: _file,
    status,
    error,
    onFileSelect,
    onCancel
}: ExtractionUploadViewProps) {
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [isDragging, setIsDragging] = useState(false)

    const handleFileSelect = (selectedFile: File | null | undefined) => {
        if (selectedFile) onFileSelect(selectedFile)
    }

    // Determine if we're in a processing state (excludes idle and ready states)
    const isActiveProcessing = isProcessingStatus(status) && !isReviewNeededStatus(status) && !isSuccessStatus(status) && !isErrorStatus(status) && status !== 'idle'

    // Get human-readable status message
    const getProcessingMessage = () => {
        if (status === EXTRACTION_STATUS.UPLOADING) {
            return '문서를 업로드하고 있습니다'
        }
        return STATUS_LABELS[status] || 'AI가 문서를 분석하고 있습니다'
    }

    // Processing state - show spinner when actively processing
    if (isActiveProcessing) {
        return (
            <motion.div
                key="processing"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                className="h-full flex flex-col items-center justify-center p-8 text-center"
            >
                <div className="relative w-32 h-32 mb-8">
                    <div className="absolute inset-0 border-4 border-muted rounded-full" />
                    <div className="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin" />
                    <div className="absolute inset-0 flex items-center justify-center">
                        <FileText className="w-10 h-10 text-primary animate-pulse" />
                    </div>
                </div>

                <h2 className="text-2xl font-bold mb-2">
                    {getProcessingMessage()}
                </h2>
                <p className="text-muted-foreground mb-8">잠시만 기다려주세요...</p>

                <Button variant="outline" onClick={onCancel}>
                    취소하기
                </Button>
            </motion.div>
        )
    }

    // Upload state
    return (
        <motion.div
            key="upload"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="h-full flex flex-col items-center justify-center p-8"
        >
            <Card
                className={cn(
                    "w-full max-w-2xl h-[400px] flex flex-col items-center justify-center border-2 border-dashed transition-all duration-300 relative overflow-hidden",
                    isDragging
                        ? "border-primary bg-primary/5 shadow-lg scale-[1.02]"
                        : "border-muted-foreground/20 hover:border-primary/50 hover:bg-muted/30"
                )}
                onDrop={(e) => {
                    e.preventDefault()
                    setIsDragging(false)
                    handleFileSelect(e.dataTransfer.files?.[0])
                }}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={(e) => { e.preventDefault(); setIsDragging(false) }}
                onClick={() => fileInputRef.current?.click()}
            >
                <div className="flex flex-col items-center z-10">
                    <div className={cn(
                        "w-20 h-20 rounded-full flex items-center justify-center mb-6 transition-colors",
                        isDragging ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
                    )}>
                        <Upload className="w-10 h-10" />
                    </div>

                    <h3 className="text-xl font-bold mb-2">문서를 여기에 놓으세요</h3>
                    <p className="text-muted-foreground mb-8 text-center max-w-xs">
                        또는 클릭하여 파일을 선택하세요<br />(PDF, 이미지 지원)
                    </p>

                    <Button size="lg" className="min-w-[180px]">
                        파일 선택하기
                    </Button>
                </div>

                {/* Error Banner */}
                {isErrorStatus(status) && error && (
                    <div className="absolute bottom-0 left-0 right-0 bg-destructive text-destructive-foreground p-4 text-center text-sm font-medium flex items-center justify-center gap-2 animate-in slide-in-from-bottom-5">
                        <AlertTriangle className="w-4 h-4" />
                        {error}
                    </div>
                )}

                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(e) => handleFileSelect(e.target.files?.[0])}
                    className="hidden"
                />
            </Card>

            <div className="mt-8">
                <Button variant="ghost" onClick={onCancel}>
                    <X className="w-4 h-4 mr-2" /> 목록으로 돌아가기
                </Button>
            </div>
        </motion.div>
    )
}
