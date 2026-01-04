import { useState } from 'react'
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { CheckCircle2, FileText, AlertCircle, ChevronDown, ChevronRight } from "lucide-react"
import type { SubDocument } from '../types'
import { isSuccessStatus } from '../constants/status'

interface DocumentDeckProps {
    subDocuments: SubDocument[]
    selectedIndex: number
    onSelect: (index: number) => void
}

export function DocumentDeck({ subDocuments, selectedIndex, onSelect }: DocumentDeckProps) {
    // Collapsed by default, only expand when user clicks
    const [isCollapsed, setIsCollapsed] = useState(true)

    if (!subDocuments || subDocuments.length <= 1) return null

    return (
        <div className={cn(
            "border-r bg-muted/10 flex flex-col h-full transition-all duration-200",
            isCollapsed ? "w-12" : "w-64"
        )}>
            {/* Header - Always visible, clickable to toggle */}
            <button
                onClick={() => setIsCollapsed(!isCollapsed)}
                className="p-3 border-b bg-card shrink-0 flex items-center gap-2 hover:bg-muted/50 transition-colors w-full"
            >
                {isCollapsed ? (
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                )}
                <FileText className="w-4 h-4 text-blue-500" />
                {!isCollapsed && (
                    <span className="font-semibold text-sm">
                        문서 목록 ({subDocuments.length})
                    </span>
                )}
            </button>

            {/* Document List - Only show when expanded */}
            {!isCollapsed && (
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
            )}

            {/* Collapsed state: show selected document indicator */}
            {isCollapsed && (
                <div className="flex-1 flex flex-col items-center pt-2 gap-1">
                    {subDocuments.map((doc, idx) => (
                        <button
                            key={idx}
                            onClick={() => {
                                onSelect(idx)
                                setIsCollapsed(false) // Expand when selecting
                            }}
                            className={cn(
                                "w-8 h-8 rounded-md flex items-center justify-center text-xs font-medium transition-all",
                                selectedIndex === idx
                                    ? "bg-primary text-primary-foreground"
                                    : "bg-muted hover:bg-muted/80 text-muted-foreground"
                            )}
                            title={`문서 #${doc.index}`}
                        >
                            {doc.index}
                        </button>
                    ))}
                </div>
            )}
        </div>
    )
}
