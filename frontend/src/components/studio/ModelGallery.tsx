import { useState } from 'react'
import { clsx } from 'clsx'
import { Plus, Trash2, LayoutTemplate, Search, Copy, Loader2, LayoutGrid, List } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Model } from '../../types/model'

interface ModelGalleryProps {
    models: Model[]
    loading: boolean
    searchQuery: string
    onSearchChange: (query: string) => void
    onNewModel: () => void
    onEditModel: (model: Model) => void
    onDeleteModel: (id: string) => void
    onCopyModel?: (id: string, e: React.MouseEvent) => void
    copyingId?: string | null
}

export function ModelGallery({
    models,
    loading,
    searchQuery,
    onSearchChange,
    onNewModel,
    onEditModel,
    onDeleteModel,
    onCopyModel,
    copyingId
}: ModelGalleryProps) {
    const [viewMode, setViewMode] = useState<'card' | 'list'>('card')
    const filteredModels = models.filter(
        model =>
            model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (model.description && model.description.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    return (
        <div className="h-[calc(100vh-80px)] p-6 font-sans overflow-y-auto custom-scrollbar">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-black text-foreground mb-1">모델 스튜디오</h2>
                    <p className="text-sm text-muted-foreground">추출 모델을 생성하고 관리하세요</p>
                </div>
                <Button onClick={onNewModel} className="gap-2">
                    <Plus className="w-4 h-4" />
                    새 모델 만들기
                </Button>
            </div>

            {loading ? (
                <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
            ) : (
                <>
                    <div className="mb-6 flex justify-between items-center gap-4">
                        <div className="relative max-w-md w-full">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <input
                                type="text"
                                placeholder="모델 검색..."
                                value={searchQuery}
                                onChange={(e) => onSearchChange(e.target.value)}
                                className="w-full pl-9 pr-4 py-2 bg-card border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all font-medium"
                            />
                        </div>
                        <div className="flex bg-muted/50 p-1 rounded-lg border border-border/50 shrink-0">
                            <button
                                onClick={() => setViewMode('card')}
                                className={clsx(
                                    "p-2 rounded-md transition-all",
                                    viewMode === 'card' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <LayoutGrid className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setViewMode('list')}
                                className={clsx(
                                    "p-2 rounded-md transition-all",
                                    viewMode === 'list' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <List className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    <div className={clsx(
                        "gap-6",
                        viewMode === 'card' ? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" : "flex flex-col"
                    )}>
                        {filteredModels.map((model) => (
                            <div
                                key={model.id}
                                className={clsx(
                                    "group cursor-pointer",
                                    viewMode === 'card' ? "h-full" : "w-full",
                                    model.is_active === false && "opacity-60"
                                )}
                                onClick={() => onEditModel(model)}
                            >
                                <div className={clsx(
                                    "relative p-[2px] transition-all duration-300",
                                    viewMode === 'card' ? "rounded-2xl" : "rounded-xl",
                                    model.is_active === false
                                        ? "bg-muted-foreground/30"
                                        : "bg-gradient-to-br from-border to-border hover:from-primary hover:to-chart-5"
                                )}>
                                    <div className={clsx(
                                        "bg-card transition-all duration-300 group-hover:shadow-xl",
                                        viewMode === 'card' ? "rounded-2xl p-5 h-full flex flex-col" : "rounded-xl p-4 flex items-center justify-between gap-4"
                                    )}>
                                        <div className={clsx(
                                            "flex items-start justify-between",
                                            viewMode === 'card' ? "mb-3" : "shrink-0 gap-4 w-12"
                                        )}>
                                            <div className={clsx(
                                                "p-2.5 rounded-xl group-hover:scale-110 transition-transform",
                                                model.is_active === false
                                                    ? "bg-muted-foreground/20"
                                                    : "bg-gradient-to-br from-primary/20 to-chart-5/20"
                                            )}>
                                                <LayoutTemplate className={clsx(
                                                    "w-5 h-5",
                                                    model.is_active === false ? "text-muted-foreground" : "text-primary"
                                                )} />
                                            </div>
                                            {viewMode === 'card' && (
                                                <div className="flex items-center gap-1">
                                                    {model.is_active === false && (
                                                        <span className="px-2 py-0.5 text-[10px] bg-muted-foreground/20 text-muted-foreground rounded-full">
                                                            숨김
                                                        </span>
                                                    )}
                                                    {onCopyModel && (
                                                        <button
                                                            onClick={(e) => onCopyModel(model.id, e)}
                                                            disabled={copyingId === model.id}
                                                            className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-primary/10 hover:text-primary text-muted-foreground rounded-lg transition-all"
                                                        >
                                                            {copyingId === model.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            onDeleteModel(model.id)
                                                        }}
                                                        className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-lg transition-all"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        <div className={clsx(
                                            viewMode === 'card' ? "" : "flex-1 min-w-0"
                                        )}>
                                            <div className="flex items-center gap-2 mb-1">
                                                <h3 className={clsx(
                                                    "font-bold text-base transition-colors",
                                                    model.is_active === false
                                                        ? "text-muted-foreground"
                                                        : "text-foreground group-hover:text-primary",
                                                    viewMode === 'list' && "truncate"
                                                )}>
                                                    {model.name}
                                                </h3>
                                                {viewMode === 'list' && model.is_active === false && (
                                                    <span className="px-2 py-0.5 text-[10px] bg-muted-foreground/20 text-muted-foreground rounded-full whitespace-nowrap">
                                                        숨김
                                                    </span>
                                                )}
                                            </div>
                                            <p className={clsx(
                                                "text-xs text-muted-foreground line-clamp-2",
                                                viewMode === 'card' ? "mb-4" : ""
                                            )}>
                                                {model.description || '설명 없음'}
                                            </p>
                                        </div>

                                        <div className={clsx(
                                            "flex items-center text-xs",
                                            viewMode === 'card' ? "justify-between mt-auto w-full" : "shrink-0 gap-6 border-l border-border/50 pl-6 w-64"
                                        )}>
                                            <span className="text-muted-foreground">{model.fields?.length || 0}개 필드</span>
                                            <span className={clsx(
                                                "px-2 py-1 rounded-full font-medium",
                                                model.is_active === false
                                                    ? "bg-muted-foreground/10 text-muted-foreground"
                                                    : "bg-primary/10 text-primary"
                                            )}>
                                                {model.data_structure?.toUpperCase() || 'DATA'}
                                            </span>
                                            {viewMode === 'list' && (
                                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    {onCopyModel && (
                                                        <button
                                                            onClick={(e) => onCopyModel(model.id, e)}
                                                            disabled={copyingId === model.id}
                                                            className="p-1.5 hover:bg-primary/10 hover:text-primary text-muted-foreground rounded-lg transition-all"
                                                        >
                                                            {copyingId === model.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            onDeleteModel(model.id)
                                                        }}
                                                        className="p-1.5 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-lg transition-all"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {filteredModels.length === 0 && (
                            <div className="col-span-full py-12 text-center text-muted-foreground border border-dashed border-border rounded-2xl bg-card/50">
                                "{searchQuery}"에 해당하는 모델이 없습니다.
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}
