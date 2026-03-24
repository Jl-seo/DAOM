/* eslint-disable @typescript-eslint/no-unused-expressions */
/* eslint-disable react-hooks/exhaustive-deps */
import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { modelsApi } from '@/lib/api'
import { useExtractionActions } from '@/hooks/useExtractionActions'

// Context & Types
import { ExtractionProvider, useExtraction } from '../context/ExtractionContext'
import { EXTRACTION_STATUS } from '../constants/status'

// Components
import { ExtractionTabsHeader } from './ExtractionTabsHeader'
import { ExtractionHistoryView } from './ExtractionHistoryView'
import { ExtractionUploadView } from './ExtractionUploadView'
import { ExtractionReviewView } from './ExtractionReviewView'
import { AggregatedDataView } from './AggregatedDataView'
import { ComparisonWorkspace } from '../../comparison/ComparisonWorkspace'

interface DocumentExtractionViewProps {
    modelId: string
    initialFile?: File | null
    onFileConsumed?: () => void
    jobId?: string
    logId?: string
}

function ExtractionContainer({ modelId, initialFile, onFileConsumed }: { modelId: string, initialFile?: File | null, onFileConsumed?: () => void }) {
    const {
        model, setModel,
        activeStep, setActiveStep,
        status,
        file, fileUrl,
        filename,
        candidateFileUrl,
        candidateFileUrls,
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
        loadFromHistory,
        currentLogId
    } = useExtraction()

    const { handleUnmask } = useExtractionActions({ modelId })

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
            import.meta.env.DEV && console.log('Quick Extraction: Processing initial file', initialFile.name)
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
            {/* Header (Tabs) - Shows only during extraction flow */}
            {activeStep !== 'history' && activeStep !== 'aggregated_data' && (
                <ExtractionTabsHeader
                    activeStep={activeStep}
                    modelName={model.name}
                    modelId={modelId}
                    onStepChange={setActiveStep}
                    onCancel={handleCancelPreview}
                    hasData={!!previewData || !!candidateFileUrls?.length}
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
                        onViewAggregated={() => setActiveStep('aggregated_data')}
                    />
                )}

                {/* Aggregated Data View */}
                {activeStep === 'aggregated_data' && (
                    <AggregatedDataView
                        model={model}
                        onBack={() => setActiveStep('history')}
                    />
                )}

                {/* 2. Upload / Processing View */}
                {activeStep === 'upload' && (
                    <ExtractionUploadView
                        file={file}
                        status={status}
                        model={model}
                        onFileSelect={processFile}
                        onCancel={() => {
                            handleReset()
                            setActiveStep('history')
                        }}
                    />
                )}

                {/* 3. Review / Edit View */}
                {(activeStep === 'raw_data' || activeStep === 'refined_data') && (
                    model?.model_type === 'comparison' ? (
                        <ComparisonWorkspace
                            fileUrl={fileUrl || ''}
                            candidateFileUrl={candidateFileUrl || ''}
                            candidateFileUrls={candidateFileUrls || []}
                            comparisonResult={previewData?.comparison_result || null}
                            comparisons={previewData?.comparisons || []}
                            onRetry={handleRetry}
                            isRefining={status === EXTRACTION_STATUS.REFINING}
                            excelColumns={model?.excel_columns}
                        />
                    ) : (
                        <ExtractionReviewView
                            // Data
                            previewData={previewData}
                            result={result}
                            model={model}
                            highlights={highlights}
                            isRawData={activeStep === 'raw_data'}

                            // State
                            selectedSubDocIndex={selectedSubDocIndex}
                            selectedFieldKey={selectedFieldKey}

                            // File Info
                            file={file}
                            fileUrl={fileUrl || null}
                            filename={filename}

                            // Actions
                            onSubDocSelect={setSelectedSubDocIndex}
                            onFieldSelect={setSelectedFieldKey}
                            onRetry={handleRetry}
                            onReset={handleReset}
                            onUnmask={currentLogId ? (fieldKey) => handleUnmask(currentLogId, fieldKey) : undefined}
                            onSave={(guide, other) => {
                                // Wrapper to match signature if needed, or pass directly if signatures match
                                // handleConfirmSelection takes (selectedColumns, editedGuide, editedOther)
                                // We can ignore selectedColumns (first arg) for auto-save of content
                                handleConfirmSelection([], guide, other)
                            }}
                        />
                    )
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
    // key={modelId} forces React to unmount/remount the entire tree when switching models
    // This ensures all extraction state is reset cleanly
    return (
        <ExtractionProvider key={props.modelId} modelId={props.modelId} initialJobId={props.jobId} initialLogId={props.logId}>
            <ExtractionContainer {...props} />
        </ExtractionProvider>
    )
}
