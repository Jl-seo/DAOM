import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { modelsApi } from '@/lib/api'

// Context & Types
import { ExtractionProvider, useExtraction } from '../context/ExtractionContext'

// Components
import { ExtractionWizardHeader } from './ExtractionWizardHeader'
import { ExtractionHistoryView } from './ExtractionHistoryView'
import { ExtractionUploadView } from './ExtractionUploadView'
import { ExtractionReviewView } from './ExtractionReviewView'

interface DocumentExtractionViewProps {
    modelId: string
    initialFile?: File | null
    onFileConsumed?: () => void
}

function ExtractionContainer({ modelId, initialFile, onFileConsumed }: { modelId: string, initialFile?: File | null, onFileConsumed?: () => void }) {
    const {
        model, setModel,
        activeStep, setActiveStep,
        status,
        file, fileUrl,
        previewData,
        result,
        selectedSubDocIndex, setSelectedSubDocIndex,
        selectedFieldKey, setSelectedFieldKey,
        highlights,
        processFile,
        handleConfirmSelection,
        handleRetry,
        handleReset,
        handleCancelPreview,
        loadFromHistory
    } = useExtraction()

    // Track if initial file was already processed to prevent infinite loops
    const initialFileProcessedRef = useRef(false)

    // -- Load Model Data --
    useEffect(() => {
        if (!modelId) return

        modelsApi.getById(modelId)
            .then(res => {
                setModel(res.data)
            })
            .catch(err => {
                console.error('Failed to load model:', err)
                toast.error('모델 정보를 불러올 수 없습니다')
            })
    }, [modelId, setModel])

    // -- Handle Initial File (Quick Extraction) --
    useEffect(() => {
        // Only process once per initialFile
        if (initialFile && model && !initialFileProcessedRef.current && status === 'idle') {
            initialFileProcessedRef.current = true
            console.log('Quick Extraction: Processing initial file', initialFile.name)
            setActiveStep('upload')
            processFile(initialFile)

            // Clear the file from parent state so it doesn't re-trigger
            if (onFileConsumed) {
                onFileConsumed()
            }
        }
    }, [initialFile, model, status])

    if (!model) {
        return (
            <div className="flex-1 flex items-center justify-center bg-muted h-full">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                <span className="ml-2 text-muted-foreground">모델 정보 로딩 중...</span>
            </div>
        )
    }

    return (
        <div className="flex flex-col h-full bg-background relative overflow-hidden">
            {/* Header (Wizard Steps) - Shows only during extraction flow */}
            {activeStep !== 'history' && (
                <ExtractionWizardHeader
                    activeStep={activeStep}
                    modelName={model.name}
                    onStepChange={setActiveStep}
                    onCancel={handleCancelPreview}
                />
            )}

            {/* Main Content Area */}
            <div className="flex-1 overflow-hidden relative flex flex-col min-w-0">

                {/* 1. History View (Default Dashboard) */}
                {activeStep === 'history' && (
                    <ExtractionHistoryView
                        model={model}
                        onNewExtraction={() => setActiveStep('upload')}
                        onSelectHistory={(log) => loadFromHistory(log)}
                    />
                )}

                {/* 2. Upload / Processing View */}
                {activeStep === 'upload' && (
                    <ExtractionUploadView
                        file={file}
                        status={status}
                        onFileSelect={processFile}
                        onCancel={() => {
                            handleReset()
                            setActiveStep('history')
                        }}
                    />
                )}

                {/* 3. Review / Edit View */}
                {(activeStep === 'review' || activeStep === 'complete') && (
                    <ExtractionReviewView
                        // Data
                        previewData={previewData}
                        result={result}
                        model={model}
                        highlights={highlights}

                        // State
                        selectedSubDocIndex={selectedSubDocIndex}
                        selectedFieldKey={selectedFieldKey}

                        // File Info
                        file={file}
                        fileUrl={fileUrl || null}

                        // Actions
                        onSubDocSelect={setSelectedSubDocIndex}
                        onFieldSelect={setSelectedFieldKey}
                        onRetry={handleRetry}
                        onReset={handleReset}
                        onSave={(guide, other) => {
                            // Wrapper to match signature if needed, or pass directly if signatures match
                            // handleConfirmSelection takes (selectedColumns, editedGuide, editedOther)
                            // We can ignore selectedColumns (first arg) for auto-save of content
                            handleConfirmSelection([], guide, other)
                        }}
                    />
                )}
            </div>
        </div>
    )
}

/**
 * Main Entry Point
 * Wraps the container with the ExtractionProvider
 */
export function DocumentExtractionView(props: DocumentExtractionViewProps) {
    return (
        <ExtractionProvider modelId={props.modelId}>
            <ExtractionContainer {...props} />
        </ExtractionProvider>
    )
}
