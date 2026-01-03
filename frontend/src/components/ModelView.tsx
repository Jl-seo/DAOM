import { DocumentExtractionView } from '../features/verification/components/DocumentExtractionView'

interface ModelViewProps {
    modelId: string
    initialFile?: File | null
    onFileConsumed?: () => void
}

export function ModelView({ modelId, initialFile, onFileConsumed }: ModelViewProps) {
    // DocumentExtractionView now handles both history list and extraction
    // History is shown first with 'New Extraction' button
    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            <DocumentExtractionView
                modelId={modelId}
                initialFile={initialFile}
                onFileConsumed={onFileConsumed}
            />
        </div>
    )
}
