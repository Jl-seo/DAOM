/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unused-vars */
import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Upload, FileText, AlertTriangle, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { AnimatedCircularProgress } from '@/components/ui/animated-circular-progress'
import { AnimatedProgressBar } from '@/components/ui/animated-progress-bar'
import { cn } from '@/lib/utils'
import type { ExtractionModel, ExtractionStatus } from '../types'
import {
    EXTRACTION_STATUS,
    STATUS_LABELS,
    STATUS_PROGRESS,
    STATUS_STEP,
    isSuccessStatus,
    isErrorStatus,
    isProcessingStatus,
    isReviewNeededStatus
} from '../constants/status'

interface ExtractionUploadViewProps {
    file: File | null
    status: ExtractionStatus
    error?: string | null
    model: ExtractionModel | null // NEW
    onFileSelect: (file: File, candidateFiles?: File[]) => void
    onCancel: () => void
}

export function ExtractionUploadView({
    file: _file,
    status,
    error,
    model,
    onFileSelect,
    onCancel
}: ExtractionUploadViewProps) {
    const { t } = useTranslation()
    const fileInputRef = useRef<HTMLInputElement>(null)
    const candidateInputRef = useRef<HTMLInputElement>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [selectedBaseline, setSelectedBaseline] = useState<File | null>(null)
    const [selectedCandidates, setSelectedCandidates] = useState<File[]>([]) // CHANGED: Array

    // Handle single file (Extraction Mode)
    const acceptTypes = '.pdf,.jpg,.jpeg,.png,.xlsx,.xls,.csv'

    const handleFileSelect = (selectedFile: File | null | undefined) => {
        if (selectedFile) onFileSelect(selectedFile)
    }

    // Determine if we're in a processing state
    const isActiveProcessing = isProcessingStatus(status) && !isReviewNeededStatus(status) && !isSuccessStatus(status) && !isErrorStatus(status) && status !== 'idle'

    // Get human-readable status message
    const getProcessingMessage = () => {
        if (status === EXTRACTION_STATUS.UPLOADING) {
            return t('extraction.processing.uploading')
        }
        return STATUS_LABELS[status] || t('extraction.processing.document_analysis')
    }

    // Processing state
    if (isActiveProcessing) {
        const progress = STATUS_PROGRESS[status] || 0
        const stepInfo = STATUS_STEP[status] || { current: 1, total: 4, label: t('common.status.processing') }

        return (
            <motion.div
                key="processing"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                className="h-full flex flex-col items-center justify-center p-8 text-center"
            >
                {/* Animated Circular Progress */}
                <AnimatedCircularProgress
                    value={progress}
                    size={140}
                    strokeWidth={12}
                    className="mb-6"
                >
                    <FileText className="w-10 h-10 text-primary animate-pulse" />
                </AnimatedCircularProgress>

                {/* Status Message */}
                <h2 className="text-2xl font-bold mb-1">
                    {getProcessingMessage()}
                </h2>
                <p className="text-muted-foreground mb-6">{t('extraction.processing.please_wait')}</p>

                {/* Progress Bar */}
                <div className="w-full max-w-md mb-4">
                    <div className="flex justify-between text-sm text-muted-foreground mb-2">
                        <span className="font-medium text-foreground">{stepInfo.label}</span>
                        <span>{progress}%</span>
                    </div>
                    <AnimatedProgressBar value={progress} size="md" />
                </div>

                <Button variant="outline" onClick={onCancel}>
                    {t('common.actions.cancel')}
                </Button>
            </motion.div>
        )
    }

    const isComparisonMode = model?.model_type === 'comparison'

    // Comparison Mode Upload View
    if (isComparisonMode) {
        return (
            <motion.div
                key="upload-comparison"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="h-full flex flex-col items-center justify-center p-8"
            >
                <h2 className="text-2xl font-bold mb-2">{t('comparison.title.upload_view')}</h2>
                <p className="text-muted-foreground mb-8">{t('comparison.upload.description')}</p>

                <div className="flex gap-6 w-full max-w-5xl h-[350px]">
                    {/* Baseline Upload */}
                    <Card
                        className={cn(
                            "flex-1 flex flex-col items-center justify-center border-2 border-dashed transition-all duration-300 relative cursor-pointer",
                            selectedBaseline ? "border-primary bg-primary/5" : "border-muted-foreground/20 hover:border-primary/50"
                        )}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <h3 className="font-bold mb-2">{t('comparison.upload.baseline_label')}</h3>
                        {selectedBaseline ? (
                            <div className="flex flex-col items-center text-primary">
                                <FileText className="w-8 h-8 mb-2" />
                                <span className="text-sm truncate max-w-[150px] font-medium">{selectedBaseline.name}</span>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center text-muted-foreground">
                                <Upload className="w-8 h-8 mb-2" />
                                <span className="text-xs">{t('comparison.upload.select_file')}</span>
                            </div>
                        )}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept={acceptTypes}
                            onChange={(e) => setSelectedBaseline(e.target.files?.[0] || null)}
                            className="hidden"
                        />
                    </Card>

                    {/* Candidate Upload (Multi-Select) */}
                    <Card
                        className={cn(
                            "flex-[1.5] flex flex-col items-center justify-start border-2 border-dashed transition-all duration-300 relative cursor-pointer overflow-hidden",
                            selectedCandidates.length > 0 ? "border-primary bg-primary/5" : "border-muted-foreground/20 hover:border-primary/50"
                        )}
                        onClick={(e) => {
                            // Prevent click when removing individual items
                            if ((e.target as HTMLElement).closest('.remove-btn')) return;
                            candidateInputRef.current?.click()
                        }}
                    >
                        <div className="w-full p-4 border-b bg-muted/20 text-center shrink-0">
                            <h3 className="font-bold">{t('comparison.upload.candidate_label')}</h3>
                            <p className="text-xs text-muted-foreground">{t('comparison.upload.multi_select')}</p>
                        </div>

                        <div className="flex-1 w-full p-4 overflow-y-auto custom-scrollbar flex flex-col items-center justify-center gap-2">
                            {selectedCandidates.length > 0 ? (
                                <div className="w-full flex flex-col gap-2">
                                    {selectedCandidates.map((file, idx) => (
                                        <div key={idx} className="flex items-center justify-between bg-background p-2 rounded-md border text-sm shadow-sm group">
                                            <div className="flex items-center gap-2 overflow-hidden">
                                                <FileText className="w-4 h-4 text-primary shrink-0" />
                                                <span className="truncate max-w-[200px]">{file.name}</span>
                                            </div>
                                            <button
                                                className="remove-btn p-1 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setSelectedCandidates(prev => prev.filter((_, i) => i !== idx));
                                                }}
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </div>
                                    ))}
                                    <div className="mt-2 text-center">
                                        <Button variant="outline" size="sm" className="h-7 text-xs">
                                            <Upload className="w-3 h-3 mr-1" /> {t('comparison.upload.add_candidate')}
                                        </Button>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center text-muted-foreground">
                                    <Upload className="w-8 h-8 mb-2" />
                                    <span className="text-xs">{t('comparison.upload.drag_drop')}</span>
                                </div>
                            )}
                        </div>

                        <input
                            ref={candidateInputRef}
                            type="file"
                            multiple // Enable multiple files
                            accept={acceptTypes}
                            onChange={(e) => {
                                if (e.target.files) {
                                    // Append new files to existing ones
                                    const newFiles = Array.from(e.target.files);
                                    setSelectedCandidates(prev => [...prev, ...newFiles]);
                                    // Reset input so same files can be selected again if needed
                                    e.target.value = '';
                                }
                            }}
                            className="hidden"
                        />
                    </Card>
                </div>

                <div className="mt-8 flex gap-4">
                    <Button variant="ghost" onClick={onCancel}>
                        <X className="w-4 h-4 mr-2" /> {t('common.actions.cancel')}
                    </Button>
                    <Button
                        size="lg"
                        disabled={!selectedBaseline || selectedCandidates.length === 0}
                        onClick={() => {
                            if (selectedBaseline && selectedCandidates.length > 0) {
                                onFileSelect(selectedBaseline, selectedCandidates as any) // Cast for compat with interface check
                            }
                        }}
                    >
                        {t('comparison.upload.start_comparison')} ({selectedCandidates.length}건)
                    </Button>
                </div>
            </motion.div>
        )
    }

    // Default Extraction Upload View
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

                    <h3 className="text-xl font-bold mb-2">{t('extraction.upload.drag_drop')}</h3>
                    <p className="text-muted-foreground mb-8 text-center max-w-xs">
                        {t('extraction.upload.click_to_select')}<br />{t('extraction.upload.supported_formats')}
                    </p>

                    <Button size="lg" className="min-w-[180px]">
                        {t('extraction.upload.select_file')}
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
                    accept={acceptTypes}
                    onChange={(e) => handleFileSelect(e.target.files?.[0])}
                    className="hidden"
                />
            </Card>

            <div className="mt-8">
                <Button variant="ghost" onClick={onCancel}>
                    <X className="w-4 h-4 mr-2" /> {t('extraction.actions.go_to_list')}
                </Button>
            </div>
        </motion.div>
    )
}
