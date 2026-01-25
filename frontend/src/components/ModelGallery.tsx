import { useState, useEffect } from 'react'
import { FileText, ArrowRight, Loader2, LayoutTemplate } from 'lucide-react'
import axios from 'axios'
import { API_CONFIG } from '../constants'
import { toast } from 'sonner'

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
}

export function ModelGallery({ onSelectModel }: ModelGalleryProps) {
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(true)

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
                {/* Header */}
                <div className="mb-8">
                    <h2 className="text-3xl font-black text-foreground mb-2">모델 갤러리</h2>
                    <p className="text-muted-foreground">모델을 선택하여 문서에서 데이터를 추출하세요</p>
                </div>

                {/* Model Grid */}
                {models.length === 0 ? (
                    <div className="text-center py-16">
                        <div className="w-20 h-20 mx-auto mb-6 bg-muted rounded-2xl flex items-center justify-center">
                            <LayoutTemplate className="w-10 h-10 text-muted-foreground" />
                        </div>
                        <h3 className="text-xl font-semibold text-foreground mb-2">아직 생성된 모델이 없습니다</h3>
                        <p className="text-muted-foreground mb-6">먼저 모델 스튜디오에서 추출 모델을 만들어보세요</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {models.map((model) => (
                            <button
                                key={model.id}
                                onClick={() => onSelectModel(model.id)}
                                className="group bg-card p-6 rounded-2xl border-2 border-border hover:border-primary shadow-sm hover:shadow-xl transition-all text-left"
                            >
                                <div className="flex items-start gap-4 mb-4">
                                    <div className="w-12 h-12 bg-gradient-to-br from-primary/20 to-chart-5/20 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                                        <FileText className="w-6 h-6 text-primary" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-lg font-bold text-foreground mb-1 group-hover:text-primary transition-colors truncate">
                                            {model.name}
                                        </h3>
                                        <p className="text-sm text-muted-foreground line-clamp-2">
                                            {model.description || '설명 없음'}
                                        </p>
                                    </div>
                                </div>

                                {/* Field Count */}
                                <div className="flex items-center justify-between text-sm mb-3">
                                    <span className="text-muted-foreground">
                                        {model.fields?.length || 0}개 추출 필드
                                    </span>
                                    {model.data_structure && (
                                        <span className="px-2 py-1 bg-primary/10 text-primary rounded-full font-medium text-xs">
                                            {model.data_structure.toUpperCase()}
                                        </span>
                                    )}
                                </div>

                                {/* Action Hint */}
                                <div className="flex items-center text-primary font-medium text-sm pt-3 border-t border-border">
                                    문서 업로드하기
                                    <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
