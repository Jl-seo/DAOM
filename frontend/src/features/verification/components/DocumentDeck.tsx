import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { CheckCircle2, FileText, AlertCircle } from "lucide-react"
import type { SubDocument } from '../types'
import { isSuccessStatus } from '../constants/status'

interface DocumentDeckProps {
    subDocuments: SubDocument[]
    selectedIndex: number
    onSelect: (index: number) => void
}

export function DocumentDeck({ subDocuments, selectedIndex, onSelect }: DocumentDeckProps) {
    if (!subDocuments || subDocuments.length <= 1) return null

    return (
        <div className="w-64 border-r bg-muted/10 flex flex-col h-full">
            <div className="p-4 border-b bg-card shrink-0">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-500" />
                    문서 목록 ({subDocuments.length})
                </h3>
            </div>
            <ScrollArea className="flex-1">
                <div className="p-2 space-y-2">
                    {subDocuments.map((doc, idx) => (
                        <button
                            key={idx}
                            onClick={() => onSelect(idx)}
                            className={cn(
                                "w-full text-left p-3 rounded-md text-sm transition-all border",
                                selectedIndex === idx
                                    ? "bg-primary/10 border-primary shadow-sm"
                                    : "bg-card border-transparent hover:bg-muted"
                            )}
                        >
                            <div className="flex justify-between items-start mb-1">
                                <span className={cn(
                                    "font-medium",
                                    selectedIndex === idx ? "text-primary" : "text-foreground"
                                )}>
                                    문서 #{doc.index}
                                </span>
                                {isSuccessStatus(doc.status) ? (
                                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                                ) : (
                                    <AlertCircle className="w-4 h-4 text-orange-500" />
                                )}
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {doc.type || 'Document'} • {doc.page_ranges?.length ?? (doc.page_range ? doc.page_range[1] - doc.page_range[0] + 1 : 1)} 페이지
                            </div>
                            <div className="text-xs text-muted-foreground mt-1">
                                P. {doc.page_ranges?.join(', ') || (doc.page_range ? `${doc.page_range[0]}-${doc.page_range[1]}` : doc.index)}
                            </div>
                        </button>
                    ))}
                </div>
            </ScrollArea>
        </div>
    )
}
