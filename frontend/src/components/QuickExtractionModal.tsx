import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload, X, FileText, ChevronRight, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { modelsApi } from '@/lib/api'
import { toast } from 'sonner'

interface QuickExtractionModalProps {
    isOpen: boolean
    onClose: () => void
    onStartExtraction: (modelId: string, file: File) => void
}

interface Model {
    id: string
    name: string
}

export function QuickExtractionModal({ isOpen, onClose, onStartExtraction }: QuickExtractionModalProps) {
    const [file, setFile] = useState<File | null>(null)
    const [selectedModelId, setSelectedModelId] = useState<string>('')
    const [models, setModels] = useState<Model[]>([])
    const [isLoadingModels, setIsLoadingModels] = useState(false)
    const [isDragging, setIsDragging] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // Load models when modal opens
    useEffect(() => {
        if (isOpen) {
            setIsLoadingModels(true)
            modelsApi.getAll()
                .then(res => {
                    setModels(res.data)
                    // Auto-select if only one model exists
                    if (res.data.length === 1) {
                        setSelectedModelId(res.data[0].id)
                    }
                })
                .catch(err => {
                    console.error('Failed to load models:', err)
                    toast.error('모델 목록을 불러올 수 없습니다')
                })
                .finally(() => setIsLoadingModels(false))
        } else {
            // Reset state on close
            setFile(null)
            setSelectedModelId('')
        }
    }, [isOpen])

    const handleFileSelect = (selectedFile: File | null | undefined) => {
        if (selectedFile) {
            if (!selectedFile.name.match(/\.(pdf|jpg|jpeg|png)$/i)) {
                toast.error('지원되지 않는 파일 형식입니다 (PDF, 이미지 가능)')
                return
            }
            setFile(selectedFile)
        }
    }

    const handleStart = () => {
        if (!file || !selectedModelId) return
        onStartExtraction(selectedModelId, file)
        onClose()
    }

    if (!isOpen) return null

    return (
        <AnimatePresence>
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="w-full max-w-lg"
                >
                    <Card className="overflow-hidden border-none shadow-2xl">
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 bg-muted/50 border-b">
                            <div className="flex items-center gap-2">
                                <div className="p-2 rounded-lg bg-primary/10 text-primary">
                                    <Upload className="w-5 h-5" />
                                </div>
                                <div>
                                    <h2 className="text-lg font-bold">빠른 추출 시작</h2>
                                    <p className="text-xs text-muted-foreground">파일을 업로드하고 모델을 선택하세요</p>
                                </div>
                            </div>
                            <Button variant="ghost" size="icon" onClick={onClose}>
                                <X className="w-5 h-5" />
                            </Button>
                        </div>

                        {/* Content */}
                        <div className="p-6 space-y-6">
                            {/* 1. File Upload Area */}
                            {!file ? (
                                <div
                                    className={cn(
                                        "h-40 border-2 border-dashed rounded-xl flex flex-col items-center justify-center cursor-pointer transition-all",
                                        isDragging
                                            ? "border-primary bg-primary/5"
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
                                    <Upload className={cn("w-8 h-8 mb-2 transition-colors", isDragging ? "text-primary" : "text-muted-foreground")} />
                                    <p className="text-sm font-medium">드래그하거나 클릭하여 파일 선택</p>
                                    <p className="text-xs text-muted-foreground mt-1">PDF, JPG, PNG 지원</p>
                                </div>
                            ) : (
                                <div className="flex items-center gap-4 p-4 border rounded-xl bg-muted/20 relative group">
                                    <div className="p-3 bg-red-100 text-red-600 rounded-lg">
                                        <FileText className="w-6 h-6" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="font-medium truncate">{file.name}</p>
                                        <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-muted-foreground hover:text-destructive"
                                        onClick={(e) => { e.stopPropagation(); setFile(null); }}
                                    >
                                        변경
                                    </Button>
                                </div>
                            )}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png"
                                onChange={(e) => handleFileSelect(e.target.files?.[0])}
                                className="hidden"
                            />

                            {/* 2. Model Selection */}
                            <div className="space-y-3">
                                <label className="text-sm font-medium flex items-center gap-2">
                                    <span className="w-5 h-5 rounded-full bg-muted flex items-center justify-center text-xs font-bold ring-1 ring-border">2</span>
                                    적용할 모델 선택
                                </label>
                                {isLoadingModels ? (
                                    <div className="h-10 flex items-center px-3 text-sm text-muted-foreground bg-muted/20 rounded-md">
                                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                        모델 목록 불러오는 중...
                                    </div>
                                ) : models.length === 0 ? (
                                    <div className="h-10 flex items-center px-3 text-sm text-destructive bg-destructive/5 rounded-md border border-destructive/20">
                                        사용 가능한 모델이 없습니다. 모델부터 생성해주세요.
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-2 max-h-40 overflow-y-auto pr-1">
                                        {models.map(model => (
                                            <button
                                                key={model.id}
                                                onClick={() => setSelectedModelId(model.id)}
                                                className={cn(
                                                    "flex items-center justify-between px-4 py-3 rounded-lg border text-left transition-all",
                                                    selectedModelId === model.id
                                                        ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary"
                                                        : "border-border hover:border-primary/50 hover:bg-muted/30"
                                                )}
                                            >
                                                <span className="font-medium text-sm">{model.name}</span>
                                                {selectedModelId === model.id && (
                                                    <div className="w-2 h-2 rounded-full bg-primary" />
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="px-6 py-4 bg-muted/50 border-t flex justify-end gap-3">
                            <Button variant="ghost" onClick={onClose}>취소</Button>
                            <Button
                                onClick={handleStart}
                                disabled={!file || !selectedModelId}
                                className="bg-gradient-to-r from-primary to-chart-5 hover:opacity-90"
                            >
                                추출 시작 <ChevronRight className="w-4 h-4 ml-1" />
                            </Button>
                        </div>
                    </Card>
                </motion.div>
            </div>
        </AnimatePresence>
    )
}
