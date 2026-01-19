import { useState, useEffect } from 'react'
import { Settings, Cpu, RefreshCw, Save, CheckCircle2, Plus, Palette, Building2, FileText } from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import axios from 'axios'
import { API_CONFIG } from '../constants'
import { ThemeCustomizer } from './settings/ThemeCustomizer'
import { BrandingEditor } from './settings/BrandingEditor'
import { PromptEditor } from './settings/PromptEditor'
import { Button } from '@/components/ui/button'

const API_BASE = API_CONFIG.BASE_URL

type SettingsTab = 'llm' | 'branding' | 'theme' | 'prompts'

interface LLMSettings {
    current_model: string
    available_models: string[]
    endpoint: string
}

export function AdminSettings() {
    const [activeTab, setActiveTab] = useState<SettingsTab>('llm')
    const [settings, setSettings] = useState<LLMSettings | null>(null)
    const [selectedModel, setSelectedModel] = useState('')
    const [customModel, setCustomModel] = useState('')
    const [showCustomInput, setShowCustomInput] = useState(false)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        fetchSettings()
    }, [])

    const fetchSettings = async () => {
        try {
            const res = await axios.get(`${API_BASE}/settings/llm`)
            setSettings(res.data)
            setSelectedModel(res.data.current_model)
        } catch (error) {
            console.error('Failed to load settings:', error)
            toast.error('설정을 불러올 수 없습니다')
        } finally {
            setLoading(false)
        }
    }

    const handleSave = async () => {
        const modelToSave = showCustomInput ? customModel : selectedModel
        if (!modelToSave) {
            toast.error('모델 이름을 입력하세요')
            return
        }

        setSaving(true)
        try {
            await axios.put(`${API_BASE}/settings/llm`, {
                model_name: modelToSave
            })
            toast.success(`모델이 ${modelToSave}로 변경되었습니다`)
            setShowCustomInput(false)
            setCustomModel('')
            fetchSettings()
        } catch (error) {
            console.error('Failed to save:', error)
            toast.error('모델 변경 실패')
        } finally {
            setSaving(false)
        }
    }

    const hasChanges = settings && (
        showCustomInput
            ? customModel.length > 0
            : selectedModel !== settings.current_model
    )

    const tabs = [
        { id: 'llm' as const, label: 'LLM 모델', icon: Cpu },
        { id: 'prompts' as const, label: '프롬프트', icon: FileText },
        { id: 'branding' as const, label: '사이트 설정', icon: Building2 },
        { id: 'theme' as const, label: '테마', icon: Palette },
    ]

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="max-w-3xl mx-auto p-6 font-sans">
            {/* Header */}
            <div className="mb-6">
                <h2 className="text-2xl font-black text-foreground mb-1 flex items-center gap-2">
                    <Settings className="w-6 h-6" />
                    관리자 설정
                </h2>
                <p className="text-sm text-muted-foreground">AI 모델, 브랜딩, 테마 설정</p>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-6 bg-muted p-1 rounded-lg">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={clsx(
                            "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-all",
                            activeTab === tab.id
                                ? "bg-card text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <tab.icon className="w-4 h-4" />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            {activeTab === 'llm' && (
                <div className="bg-card rounded-xl shadow-sm border border-border p-6">
                    <div className="flex items-center gap-2 mb-4">
                        <div className="bg-gradient-to-r from-primary to-chart-5 p-2 rounded-lg">
                            <Cpu className="w-4 h-4 text-primary-foreground" />
                        </div>
                        <h3 className="font-bold text-base text-foreground">LLM 모델 설정</h3>
                    </div>

                    <div className="space-y-4">
                        {/* Current Model */}
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">현재 모델</label>
                            <div className="flex items-center gap-2 text-sm text-foreground">
                                <CheckCircle2 className="w-4 h-4 text-chart-2" />
                                <span className="font-mono bg-muted px-2 py-1 rounded">{settings?.current_model}</span>
                            </div>
                        </div>

                        {/* Model Selection Mode Toggle */}
                        <div className="flex gap-2">
                            <Button
                                variant={!showCustomInput ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setShowCustomInput(false)}
                            >
                                목록에서 선택
                            </Button>
                            <Button
                                variant={showCustomInput ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => setShowCustomInput(true)}
                            >
                                <Plus className="w-3 h-3 mr-1" />
                                직접 입력
                            </Button>
                        </div>

                        {/* Model Selection */}
                        {showCustomInput ? (
                            <div>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">
                                    배포 이름 직접 입력
                                </label>
                                <input
                                    type="text"
                                    value={customModel}
                                    onChange={(e) => setCustomModel(e.target.value)}
                                    placeholder="예: my-gpt-4o-deployment"
                                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring bg-background font-mono"
                                />
                                <p className="text-xs text-muted-foreground mt-1">
                                    Azure Portal → AI Foundry → Deployments에서 확인
                                </p>
                            </div>
                        ) : (
                            <div>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">모델 선택</label>
                                <select
                                    value={selectedModel}
                                    onChange={(e) => setSelectedModel(e.target.value)}
                                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring bg-background"
                                >
                                    {settings?.available_models.map(model => (
                                        <option key={model} value={model}>{model}</option>
                                    ))}
                                </select>
                            </div>
                        )}

                        {/* Endpoint Info */}
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">엔드포인트</label>
                            <div className="p-2 bg-muted rounded text-xs font-mono text-muted-foreground break-all">
                                {settings?.endpoint}
                            </div>
                        </div>

                        {/* Save Button */}
                        <Button
                            onClick={handleSave}
                            disabled={!hasChanges || saving}
                            className="w-full"
                        >
                            {saving ? (
                                <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                            ) : (
                                <Save className="w-4 h-4 mr-2" />
                            )}
                            {saving ? '저장 중...' : hasChanges ? '변경 사항 저장' : '변경 없음'}
                        </Button>
                    </div>
                </div>
            )}

            {activeTab === 'branding' && <BrandingEditor />}
            {activeTab === 'theme' && <ThemeCustomizer />}
            {activeTab === 'prompts' && <PromptEditor />}

            {/* Info */}
            {activeTab === 'llm' && (
                <div className="mt-4 bg-primary/10 border border-primary/20 rounded-lg p-4 text-sm text-primary">
                    <strong>💡 참고:</strong> 모델 변경은 서버 재시작 없이 즉시 적용됩니다.
                </div>
            )}
        </div>
    )
}
