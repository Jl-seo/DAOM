import { useState } from 'react'
import { Eye, X as XIcon } from 'lucide-react'
import { clsx } from 'clsx'
import type { Model } from '../../types/model'
import { ExcelPreview } from '../preview/ExcelPreview'
import { JSONPreview } from '../preview/JSONPreview'
import { generateMockData } from '../../utils/mockData'

interface PreviewPanelProps {
    model: Partial<Model>
    isOpen: boolean
    onClose: () => void
    onOpen: () => void
}

type PreviewTab = 'structure' | 'excel' | 'json'

export function PreviewPanel({ model, isOpen, onClose, onOpen }: PreviewPanelProps) {
    const [activeTab, setActiveTab] = useState<PreviewTab>('structure')

    return (
        <>
            {/* Preview Panel */}
            <div
                className={clsx(
                    "shrink-0 bg-sidebar rounded-xl shadow-lg overflow-hidden flex flex-col text-sidebar-foreground relative transition-all duration-500 ease-in-out",
                    isOpen ? "w-[480px] p-4 opacity-100 translate-x-0" : "w-0 p-0 opacity-0 translate-x-20 pointer-events-none"
                )}
            >
                {isOpen && (
                    <>
                        {/* Header */}
                        <div className="flex items-center justify-between mb-4 text-sidebar-foreground">
                            <div className="flex items-center gap-1.5">
                                <Eye className="w-3 h-3 text-chart-2" />
                                <h3 className="font-bold text-[10px] tracking-wide uppercase">미리보기</h3>
                            </div>
                            <button
                                onClick={onClose}
                                className="hover:bg-sidebar-accent p-1 rounded transition-colors"
                                title="미리보기 닫기"
                            >
                                <XIcon className="w-3.5 h-3.5" />
                            </button>
                        </div>

                        {/* Tabs */}
                        <div className="mb-3">
                            <div className="flex gap-1 bg-sidebar-accent p-1 rounded-lg">
                                <button
                                    onClick={() => setActiveTab('structure')}
                                    className={clsx(
                                        "flex-1 px-2 py-1.5 rounded text-[10px] font-bold transition-all",
                                        activeTab === 'structure'
                                            ? "bg-sidebar text-sidebar-foreground"
                                            : "text-sidebar-foreground/60 hover:text-sidebar-foreground"
                                    )}
                                >
                                    구조
                                </button>
                                <button
                                    onClick={() => setActiveTab('excel')}
                                    className={clsx(
                                        "flex-1 px-2 py-1.5 rounded text-[10px] font-bold transition-all",
                                        activeTab === 'excel'
                                            ? "bg-sidebar text-sidebar-foreground"
                                            : "text-sidebar-foreground/60 hover:text-sidebar-foreground"
                                    )}
                                >
                                    Excel
                                </button>
                                <button
                                    onClick={() => setActiveTab('json')}
                                    className={clsx(
                                        "flex-1 px-2 py-1.5 rounded text-[10px] font-bold transition-all",
                                        activeTab === 'json'
                                            ? "bg-sidebar text-sidebar-foreground"
                                            : "text-sidebar-foreground/60 hover:text-sidebar-foreground"
                                    )}
                                >
                                    JSON
                                </button>
                            </div>
                        </div>

                        {/* Tab Content */}
                        <div className="flex-1 overflow-y-auto custom-scrollbar">
                            {activeTab === 'structure' && (
                                <div className="space-y-2 font-mono text-xs leading-snug">
                                    <div className="text-sidebar-foreground/50 mb-1 text-[10px]">// Simulation</div>

                                    <div className="space-y-1.5 opacity-80">
                                        <div className="flex gap-2 text-chart-5">
                                            <span className="text-sidebar-foreground/40 select-none">1</span>
                                            <div>
                                                <span className="text-sidebar-foreground/50 block text-[10px] mb-0.5"># Context</span>
                                                <span>"{model.description || '...'}"</span>
                                            </div>
                                        </div>

                                        {model.global_rules && (
                                            <div className="flex gap-2 text-chart-4 animate-in slide-in-from-left-2">
                                                <span className="text-sidebar-foreground/40 select-none">2</span>
                                                <div>
                                                    <span className="text-sidebar-foreground/50 block text-[10px] mb-0.5"># Rules</span>
                                                    <span>"{model.global_rules}"</span>
                                                </div>
                                            </div>
                                        )}

                                        <div className="flex gap-2 text-primary mt-3">
                                            <span className="text-sidebar-foreground/40 select-none">3</span>
                                            <span>extract: [</span>
                                        </div>
                                        {model.fields?.map((field, idx) => (
                                            <div key={idx} className="pl-5 space-y-0.5 animate-in slide-in-from-left-2 duration-300">
                                                <div className="text-chart-2 flex items-center gap-2">
                                                    "{field.key || 'untitled'}"
                                                    <span className="text-sidebar-foreground/40 text-[10px] px-1 border border-sidebar-border rounded ml-1">{field.type}</span>
                                                </div>
                                            </div>
                                        ))}
                                        <div className="flex gap-2 text-primary">
                                            <span className="text-sidebar-foreground/40 select-none">...</span>
                                            <span>]</span>
                                        </div>

                                        <div className="pt-2 text-sidebar-foreground/50 text-[10px]">
                                            구조: <span className="text-sidebar-foreground font-bold">{model.data_structure?.toUpperCase() || 'DATA'}</span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'excel' && (
                                <ExcelPreview
                                    data={generateMockData(model as Model)}
                                    fields={model.fields || []}
                                />
                            )}

                            {activeTab === 'json' && (
                                <JSONPreview data={generateMockData(model as Model)} />
                            )}
                        </div>

                        {/* Footer hint */}
                        <div className="mt-3 pt-3 border-t border-sidebar-border">
                            <div className="text-sidebar-foreground/40 text-[10px] text-center">
                                <kbd className="px-1 py-0.5 bg-sidebar-accent rounded text-sidebar-foreground/60">Esc</kbd> 또는 우측 × 버튼으로 닫기
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Floating Open Button */}
            {!isOpen && (
                <button
                    onClick={onOpen}
                    className="shrink-0 bg-sidebar hover:bg-sidebar-accent text-sidebar-foreground px-4 py-3 rounded-xl shadow-xl transition-all flex items-center gap-2 h-fit self-start"
                    title="미리보기 열기"
                >
                    <Eye className="w-4 h-4" />
                    <span className="text-xs font-medium">미리보기</span>
                </button>
            )}
        </>
    )
}
