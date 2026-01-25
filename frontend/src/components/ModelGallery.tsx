import { useState, useEffect } from 'react'
import { FileText, ArrowRight, Loader2, LayoutTemplate, PlusCircle, Sparkles, Search, GitCompare } from 'lucide-react'
import axios from 'axios'
import { API_CONFIG } from '../constants'
import { toast } from 'sonner'
import { useSiteConfig } from './SiteConfigProvider'

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

export function ModelGallery({ onSelectModel, onNavigate }: ModelGalleryProps) {
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
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

    const filteredModels = models.filter(model =>
        model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.description?.toLowerCase().includes(searchQuery.toLowerCase())
    )

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="flex-1 overflow-auto">
            {/* Modern Gradient Hero Section */}
            <div className="relative overflow-hidden">
                {/* Background gradient */}
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-chart-5/5 to-chart-2/5" />
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent" />

                {/* Content */}
                <div className="relative max-w-6xl mx-auto px-4 md:px-8 py-12 md:py-16">
                    <div className="flex flex-col md:flex-row items-center gap-8">
                        {/* Icon */}
                        <div className="relative">
                            <div className="w-24 h-24 md:w-28 md:h-28 bg-gradient-to-br from-primary via-chart-5 to-chart-2 rounded-3xl flex items-center justify-center shadow-2xl shadow-primary/20 rotate-3 hover:rotate-0 transition-transform duration-300">
                                <Sparkles className="w-12 h-12 md:w-14 md:h-14 text-white" />
                            </div>
                            <div className="absolute -bottom-1 -right-1 w-8 h-8 bg-chart-2 rounded-xl flex items-center justify-center shadow-lg">
                                <FileText className="w-4 h-4 text-white" />
                            </div>
                        </div>

                        {/* Text Content */}
                        <div className="text-center md:text-left flex-1">
                            <h1 className="text-4xl md:text-5xl font-black bg-gradient-to-r from-foreground via-foreground to-muted-foreground bg-clip-text text-transparent mb-3">
                                {config.siteName}
                            </h1>
                            <p className="text-lg md:text-xl text-muted-foreground mb-6 max-w-xl">
                                AI 기반 문서 분석 플랫폼. 데이터 추출부터 이미지 비교까지.
                            </p>
                            <div className="flex flex-wrap gap-3 justify-center md:justify-start">
                                <button
                                    onClick={() => onNavigate('model-studio')}
                                    className="group inline-flex items-center px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-chart-5 text-white font-semibold hover:shadow-lg hover:shadow-primary/30 hover:-translate-y-0.5 transition-all duration-200"
                                >
                                    <PlusCircle className="w-5 h-5 mr-2" />
                                    새 모델 만들기
                                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="max-w-6xl mx-auto px-4 md:px-8 py-8">
                {/* Search Bar */}
                <div className="mb-8">
                    <div className="relative max-w-md">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="모델 검색..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                        />
                    </div>
                </div>

                {/* Section Header */}
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-2xl font-bold text-foreground">모델 갤러리</h2>
                        <p className="text-muted-foreground text-sm">
                            {filteredModels.length}개의 모델이 있습니다
                        </p>
                    </div>
                </div>

                {/* Model Grid */}
                {filteredModels.length === 0 ? (
                    <div className="text-center py-20 bg-gradient-to-br from-muted/30 to-muted/10 rounded-3xl border-2 border-dashed border-border">
                        <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-muted to-background rounded-2xl flex items-center justify-center shadow-inner">
                            <LayoutTemplate className="w-10 h-10 text-muted-foreground" />
                        </div>
                        <h3 className="text-xl font-bold text-foreground mb-2">
                            {searchQuery ? '검색 결과가 없습니다' : '아직 생성된 모델이 없습니다'}
                        </h3>
                        <p className="text-muted-foreground mb-8 text-sm max-w-md mx-auto">
                            {searchQuery ? '다른 검색어를 시도해보세요' : '모델 스튜디오에서 첫 번째 추출 모델을 만들어보세요'}
                        </p>
                        {!searchQuery && (
                            <button
                                onClick={() => onNavigate('model-studio')}
                                className="inline-flex items-center px-5 py-2.5 rounded-xl bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
                            >
                                <PlusCircle className="w-4 h-4 mr-2" />
                                모델 생성하기
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {filteredModels.map((model) => (
                            <button
                                key={model.id}
                                onClick={() => onSelectModel(model.id)}
                                className="group relative flex flex-col bg-card p-5 rounded-2xl border border-border hover:border-primary/50 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 text-left overflow-hidden"
                            >
                                {/* Hover gradient overlay */}
                                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-chart-5/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                                <div className="relative z-10">
                                    {/* Icon and Type Badge */}
                                    <div className="flex items-start justify-between mb-4">
                                        <div className="w-12 h-12 bg-gradient-to-br from-primary/10 to-chart-5/10 rounded-xl flex items-center justify-center group-hover:scale-110 group-hover:rotate-3 transition-all duration-300">
                                            {model.model_type === 'comparison' ? (
                                                <GitCompare className="w-6 h-6 text-chart-5" />
                                            ) : (
                                                <FileText className="w-6 h-6 text-primary" />
                                            )}
                                        </div>
                                        {model.model_type === 'comparison' && (
                                            <span className="px-2 py-1 bg-chart-5/10 text-chart-5 rounded-lg font-bold text-[10px] tracking-wider uppercase border border-chart-5/20">
                                                비교
                                            </span>
                                        )}
                                    </div>

                                    {/* Title & Description */}
                                    <h3 className="text-lg font-bold text-foreground mb-2 group-hover:text-primary transition-colors line-clamp-1">
                                        {model.name}
                                    </h3>
                                    <p className="text-sm text-muted-foreground line-clamp-2 mb-4 min-h-[2.5rem]">
                                        {model.description || '설명 없음'}
                                    </p>

                                    {/* Footer */}
                                    <div className="flex items-center justify-between pt-4 border-t border-border/50 group-hover:border-primary/20 transition-colors">
                                        <span className="text-xs text-muted-foreground bg-muted/50 px-2.5 py-1 rounded-lg font-medium">
                                            {model.fields?.length || 0}개 필드
                                        </span>
                                        <span className="text-primary text-sm font-medium flex items-center group-hover:translate-x-1 transition-transform">
                                            시작
                                            <ArrowRight className="w-4 h-4 ml-1" />
                                        </span>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
