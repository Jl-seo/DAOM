import { useState, useEffect, useMemo } from 'react'
import { FileText, ArrowRight, Loader2, LayoutTemplate, PlusCircle, Sparkles, Search, GitCompare, Layers } from 'lucide-react'
import axios from 'axios'
import { API_CONFIG } from '../constants'
import { toast } from 'sonner'
import { useSiteConfig } from './SiteConfigProvider'
import clsx from 'clsx'

const API_BASE = API_CONFIG.BASE_URL

interface Model {
    id: string
    name: string
    description: string
    fields: Array<{ key: string; label: string; type: string }>
    data_structure?: string
    model_type?: 'extraction' | 'comparison'
}

interface ModelGalleryProps {
    onSelectModel: (modelId: string) => void
    onNavigate: (menuId: string) => void
}

type TabType = 'all' | 'extraction' | 'comparison'

export function ModelGallery({ onSelectModel, onNavigate }: ModelGalleryProps) {
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
    const [activeTab, setActiveTab] = useState<TabType>('all')
    const { config } = useSiteConfig()

    useEffect(() => {
        loadModels()
    }, [])

    const loadModels = async () => {
        try {
            const res = await axios.get(`${API_BASE}/models`)
            setModels(res.data)
        } catch (error) {
            toast.error('모델 목록을 불러올 수 없습니다')
        } finally {
            setLoading(false)
        }
    }

    // Count models by type
    const counts = useMemo(() => ({
        all: models.length,
        extraction: models.filter(m => m.model_type !== 'comparison').length,
        comparison: models.filter(m => m.model_type === 'comparison').length
    }), [models])

    // Filter by tab and search
    const filteredModels = useMemo(() => {
        let result = models

        // Tab filter
        if (activeTab === 'extraction') {
            result = result.filter(m => m.model_type !== 'comparison')
        } else if (activeTab === 'comparison') {
            result = result.filter(m => m.model_type === 'comparison')
        }

        // Search filter
        if (searchQuery) {
            result = result.filter(model =>
                model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                model.description?.toLowerCase().includes(searchQuery.toLowerCase())
            )
        }

        return result
    }, [models, activeTab, searchQuery])

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        )
    }

    const tabs: { key: TabType; label: string; icon: React.ReactNode; color: string }[] = [
        { key: 'all', label: '전체', icon: <Layers className="w-4 h-4" />, color: 'text-foreground' },
        { key: 'extraction', label: '추출', icon: <FileText className="w-4 h-4" />, color: 'text-primary' },
        { key: 'comparison', label: '비교', icon: <GitCompare className="w-4 h-4" />, color: 'text-chart-5' },
    ]

    return (
        <div className="flex-1 overflow-auto">
            {/* Compact Hero Section */}
            <div className="relative overflow-hidden border-b border-border">
                <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-chart-5/5 to-chart-2/5" />

                <div className="relative max-w-6xl mx-auto px-4 md:px-8 py-8">
                    <div className="flex flex-col md:flex-row items-center gap-6">
                        <div className="w-16 h-16 bg-gradient-to-br from-primary via-chart-5 to-chart-2 rounded-2xl flex items-center justify-center shadow-xl">
                            <Sparkles className="w-8 h-8 text-white" />
                        </div>

                        <div className="text-center md:text-left flex-1">
                            <h1 className="text-2xl md:text-3xl font-black text-foreground mb-1">
                                {config.siteName}
                            </h1>
                            <p className="text-muted-foreground text-sm">
                                AI 기반 문서 분석 플랫폼
                            </p>
                        </div>

                        <button
                            onClick={() => onNavigate('model-studio')}
                            className="inline-flex items-center px-5 py-2.5 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20"
                        >
                            <PlusCircle className="w-4 h-4 mr-2" />
                            새 모델
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="max-w-6xl mx-auto px-4 md:px-8 py-6">
                {/* Tab Navigation + Search */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                    {/* Tabs */}
                    <div className="flex gap-1 p-1 bg-muted/50 rounded-xl w-fit">
                        {tabs.map(tab => (
                            <button
                                key={tab.key}
                                onClick={() => setActiveTab(tab.key)}
                                className={clsx(
                                    "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                                    activeTab === tab.key
                                        ? "bg-background shadow-sm text-foreground"
                                        : "text-muted-foreground hover:text-foreground hover:bg-background/50"
                                )}
                            >
                                <span className={activeTab === tab.key ? tab.color : undefined}>
                                    {tab.icon}
                                </span>
                                {tab.label}
                                <span className={clsx(
                                    "ml-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold",
                                    activeTab === tab.key
                                        ? "bg-muted text-muted-foreground"
                                        : "bg-muted/50 text-muted-foreground/70"
                                )}>
                                    {counts[tab.key]}
                                </span>
                            </button>
                        ))}
                    </div>

                    {/* Search */}
                    <div className="relative max-w-xs w-full">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="모델 검색..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                        />
                    </div>
                </div>

                {/* Model Grid */}
                {filteredModels.length === 0 ? (
                    <div className="text-center py-16 bg-muted/30 rounded-2xl border-2 border-dashed border-border">
                        <div className="w-16 h-16 mx-auto mb-4 bg-background rounded-2xl flex items-center justify-center">
                            <LayoutTemplate className="w-8 h-8 text-muted-foreground" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-1">
                            {searchQuery ? '검색 결과가 없습니다' : `${activeTab === 'comparison' ? '비교' : activeTab === 'extraction' ? '추출' : ''} 모델이 없습니다`}
                        </h3>
                        <p className="text-muted-foreground text-sm mb-6">
                            {searchQuery ? '다른 검색어를 시도해보세요' : '새 모델을 만들어보세요'}
                        </p>
                        {!searchQuery && (
                            <button
                                onClick={() => onNavigate('model-studio')}
                                className="inline-flex items-center px-4 py-2 rounded-lg bg-primary text-white font-medium hover:bg-primary/90"
                            >
                                <PlusCircle className="w-4 h-4 mr-2" />
                                모델 만들기
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {filteredModels.map((model) => {
                            const isComparison = model.model_type === 'comparison'
                            return (
                                <button
                                    key={model.id}
                                    onClick={() => onSelectModel(model.id)}
                                    className={clsx(
                                        "group relative flex flex-col p-4 rounded-xl border-2 transition-all duration-200 text-left",
                                        "hover:shadow-lg hover:-translate-y-0.5",
                                        isComparison
                                            ? "bg-gradient-to-br from-chart-5/5 to-transparent border-chart-5/20 hover:border-chart-5/50"
                                            : "bg-card border-border hover:border-primary/50"
                                    )}
                                >
                                    {/* Type Badge */}
                                    <div className="flex items-center justify-between mb-3">
                                        <div className={clsx(
                                            "w-10 h-10 rounded-xl flex items-center justify-center",
                                            isComparison
                                                ? "bg-chart-5/10 group-hover:bg-chart-5/20"
                                                : "bg-primary/10 group-hover:bg-primary/20"
                                        )}>
                                            {isComparison
                                                ? <GitCompare className="w-5 h-5 text-chart-5" />
                                                : <FileText className="w-5 h-5 text-primary" />
                                            }
                                        </div>
                                        <span className={clsx(
                                            "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider",
                                            isComparison
                                                ? "bg-chart-5/10 text-chart-5 border border-chart-5/20"
                                                : "bg-primary/10 text-primary border border-primary/20"
                                        )}>
                                            {isComparison ? '비교' : '추출'}
                                        </span>
                                    </div>

                                    {/* Title & Description */}
                                    <h3 className={clsx(
                                        "font-bold mb-1 line-clamp-1 transition-colors",
                                        isComparison ? "group-hover:text-chart-5" : "group-hover:text-primary"
                                    )}>
                                        {model.name}
                                    </h3>
                                    <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[2rem]">
                                        {model.description || '설명 없음'}
                                    </p>

                                    {/* Footer */}
                                    <div className="flex items-center justify-between mt-auto pt-3 border-t border-border/50">
                                        <span className="text-[10px] text-muted-foreground bg-muted/50 px-2 py-1 rounded-md">
                                            {model.fields?.length || 0}개 필드
                                        </span>
                                        <span className={clsx(
                                            "text-xs font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity",
                                            isComparison ? "text-chart-5" : "text-primary"
                                        )}>
                                            시작
                                            <ArrowRight className="w-3 h-3" />
                                        </span>
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                )}
            </div>
        </div>
    )
}
