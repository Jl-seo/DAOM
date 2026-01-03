import { FileText, Zap, Shield, ArrowRight, PlusCircle, Upload, Sparkles } from 'lucide-react'
import { useSiteConfig } from './SiteConfigProvider'
import { Card } from '@/components/ui/card'

interface WelcomeScreenProps {
    onGetStarted: () => void
    onNavigate?: (menuId: string) => void
}

export function WelcomeScreen({ onGetStarted, onNavigate }: WelcomeScreenProps) {
    const { config } = useSiteConfig()

    const handleNavigate = (menuId: string) => {
        if (onNavigate) {
            onNavigate(menuId)
        } else {
            onGetStarted()
        }
    }

    return (
        <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-primary/5 via-background to-chart-5/5 p-8">
            <div className="max-w-5xl mx-auto w-full">
                {/* Logo/Title */}
                <div className="mb-12 text-center">
                    <div className="w-20 h-20 bg-gradient-to-br from-primary to-chart-5 rounded-2xl mx-auto mb-6 flex items-center justify-center shadow-xl">
                        <FileText className="w-10 h-10 text-primary-foreground" />
                    </div>
                    <h1 className="text-5xl font-bold text-foreground mb-4">
                        {config.siteName}에 오신 것을 환영합니다
                    </h1>
                    <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                        AI 기반 문서 분석 서비스로 비정형 데이터를 정형화된 정보로 자동 변환하세요
                    </p>
                </div>

                {/* Quick Actions */}
                <div className="grid md:grid-cols-2 gap-6 mb-12">
                    <button
                        onClick={() => handleNavigate('model-studio')}
                        className="group bg-card p-8 rounded-2xl border-2 border-border hover:border-primary shadow-sm hover:shadow-xl transition-all text-left"
                    >
                        <div className="flex items-start gap-4">
                            <div className="w-14 h-14 bg-gradient-to-br from-primary to-primary/80 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform shadow-lg">
                                <PlusCircle className="w-7 h-7 text-primary-foreground" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-foreground mb-2 group-hover:text-primary transition-colors">
                                    추출 모델 만들기
                                </h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    새로운 문서 타입에 맞는 추출 모델을 생성하고 필드를 정의하세요
                                </p>
                                <div className="flex items-center text-primary font-medium text-sm">
                                    모델 스튜디오로 이동
                                    <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
                                </div>
                            </div>
                        </div>
                    </button>

                    <button
                        onClick={() => handleNavigate('model-gallery')}
                        className="group bg-card p-8 rounded-2xl border-2 border-border hover:border-chart-5 shadow-sm hover:shadow-xl transition-all text-left"
                    >
                        <div className="flex items-start gap-4">
                            <div className="w-14 h-14 bg-gradient-to-br from-chart-5 to-chart-5/80 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform shadow-lg">
                                <Upload className="w-7 h-7 text-primary-foreground" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-foreground mb-2 group-hover:text-chart-5 transition-colors">
                                    문서 추출 시작하기
                                </h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    기존 모델을 선택하여 문서를 업로드하고 데이터를 추출하세요
                                </p>
                                <div className="flex items-center text-chart-5 font-medium text-sm">
                                    모델 선택하기
                                    <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
                                </div>
                            </div>
                        </div>
                    </button>
                </div>

                {/* Features */}
                <div className="grid md:grid-cols-3 gap-6">
                    <Card className="bg-card/60 backdrop-blur p-6">
                        <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                            <Zap className="w-6 h-6 text-primary" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-2 text-center">빠른 추출</h3>
                        <p className="text-sm text-muted-foreground text-center">
                            Azure AI Document Intelligence로 정확하게 문서를 분석합니다
                        </p>
                    </Card>

                    <Card className="bg-card/60 backdrop-blur p-6">
                        <div className="w-12 h-12 bg-chart-5/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                            <Sparkles className="w-6 h-6 text-chart-5" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-2 text-center">AI 보정</h3>
                        <p className="text-sm text-muted-foreground text-center">
                            GPT 모델로 추출된 데이터를 검증하고 보정합니다
                        </p>
                    </Card>

                    <Card className="bg-card/60 backdrop-blur p-6">
                        <div className="w-12 h-12 bg-chart-2/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                            <Shield className="w-6 h-6 text-chart-2" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-2 text-center">간편한 내보내기</h3>
                        <p className="text-sm text-muted-foreground text-center">
                            Excel 다운로드 또는 Power Automate로 시스템 연동
                        </p>
                    </Card>
                </div>
            </div>
        </div>
    )
}
