import { useState, useEffect } from 'react'
import { FileText, ArrowRight, Loader2, LayoutTemplate, PlusCircle } from 'lucide-react'
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
}

interface ModelGalleryProps {
    onSelectModel: (modelId: string) => void
    onNavigate: (menuId: string) => void
}

export function ModelGallery({ onSelectModel, onNavigate }: ModelGalleryProps) {
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(true)
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

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="flex-1 p-4 md:p-8 overflow-auto bg-background">
            <div className="max-w-6xl mx-auto">
                {/* Hero Section */}
                <div className="mb-12 text-center md:text-left">
                    <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
                        <div className="w-16 h-16 md:w-20 md:h-20 bg-gradient-to-br from-primary to-chart-5 rounded-2xl flex items-center justify-center shadow-lg shrink-0">
                            <FileText className="w-8 h-8 md:w-10 md:h-10 text-primary-foreground" />
                        </div>
                        <div>
                            <h1 className="text-3xl md:text-4xl font-black text-foreground mb-2">
                                {config.siteName}
                            </h1>
                            <p className="text-lg text-muted-foreground mb-4 max-w-2xl">
                                AI 기반 문서 분석 서비스입니다. 기존 모델을 선택하거나 새로운 문서를 위한 추출 모델을 만들어보세요.
                            </p>
                            <div className="flex flex-wrap gap-3 justify-center md:justify-start">
                                <button
                                    onClick={() => onNavigate('model-studio')}
                                    className="inline-flex items-center px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors shadow-sm"
                                >
                                    <PlusCircle className="w-4 h-4 mr-2" />
                                    새로운 모델 만들기
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="border-b border-border mb-8" />

                {/* Header */}
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold text-foreground mb-1">모델 갤러리</h2>
                        <p className="text-muted-foreground text-sm">사용 가능한 문서 추출 모델 목록입니다</p>
                    </div>
                </div>

                {/* Model Grid */}
                {models.length === 0 ? (
                    <div className="text-center py-16 bg-muted/30 rounded-3xl border-2 border-dashed border-border">
                        <div className="w-16 h-16 mx-auto mb-4 bg-background rounded-2xl flex items-center justify-center shadow-sm">
                            <LayoutTemplate className="w-8 h-8 text-muted-foreground" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-1">아직 생성된 모델이 없습니다</h3>
                        <p className="text-muted-foreground mb-6 text-sm">먼저 모델 스튜디오에서 추출 모델을 만들어보세요</p>
                        <button
                            onClick={() => onNavigate('model-studio')}
                            className="text-primary font-medium hover:underline inline-flex items-center"
                        >
                            모델 생성하러 가기
                            <ArrowRight className="w-4 h-4 ml-1" />
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {models.map((model) => (
                            <button
                                key={model.id}
                                onClick={() => onSelectModel(model.id)}
                                className="group flex flex-col h-full bg-card p-6 rounded-2xl border-2 border-border hover:border-primary shadow-sm hover:shadow-xl transition-all text-left"
                            >
                                <div className="flex items-start gap-4 mb-4">
                                    <div className="w-12 h-12 bg-gradient-to-br from-primary/10 to-chart-5/10 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                                        <FileText className="w-6 h-6 text-primary" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-lg font-bold text-foreground mb-1 group-hover:text-primary transition-colors truncate">
                                            {model.name}
                                        </h3>
                                        <p className="text-sm text-muted-foreground line-clamp-2 min-h-[2.5rem]">
                                            {model.description || '설명 없음'}
                                        </p>
                                    </div>
                                </div>

                                <div className="mt-auto">
                                    {/* Field Count */}
                                    <div className="flex items-center justify-between text-sm mb-4">
                                        <span className="text-muted-foreground bg-muted px-2 py-1 rounded-md text-xs font-medium">
                                            {model.fields?.length || 0}개 필드
                                        </span>
                                        {model.data_structure && (
                                            <span className="px-2 py-1 bg-chart-1/10 text-chart-1 rounded-md font-bold text-[10px] tracking-wider uppercase border border-chart-1/20">
                                                {model.data_structure}
                                            </span>
                                        )}
                                    </div>

                                    {/* Action Hint */}
                                    <div className="flex items-center text-primary font-medium text-sm pt-3 border-t border-border group-hover:border-primary/20 transition-colors">
                                        문서 업로드하기
                                        <ArrowRight className="w-4 h-4 ml-auto group-hover:translate-x-1 transition-transform" />
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
