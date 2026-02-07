import { useParams } from 'react-router-dom'
import { DocumentExtractionView } from '../features/verification/components/DocumentExtractionView'

interface ModelViewProps {
    initialFile?: File | null
    onFileConsumed?: () => void
}

export function ModelView({ initialFile, onFileConsumed }: ModelViewProps) {
    const { modelId, jobId, logId } = useParams<{ modelId?: string; jobId?: string; logId?: string }>()

    // If we have a jobId, we'll need to fetch the job details to get the modelId
    // For now, we'll use modelId if available
    const effectiveModelId = modelId || ''

    // DocumentExtractionView now handles both history list and extraction
    // History is shown first with 'New Extraction' button
    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            <DocumentExtractionView
                modelId={effectiveModelId}
                initialFile={initialFile}
                onFileConsumed={onFileConsumed}
                jobId={jobId}
                logId={logId}
            />
        </div>
    )
}
