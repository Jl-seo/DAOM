import { useState } from 'react'
import {
    Plus, Trash2, Save, ArrowLeft, Wand2,
    LayoutTemplate, RefreshCw, Edit, Sliders
} from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import { DEFAULTS, MESSAGES } from '../constants'
import { useModels } from '../hooks/useModels'
import type { Model, Field } from '../types/model'
import type { TemplateConfig } from '../types/template'
import { defaultTemplateConfig } from '../types/template'
import { Card } from '@/components/ui/icon-card'
import { Button } from '@/components/ui/button'
import { DataStructureSelector } from './studio/DataStructureSelector'
import { FieldEditorTable } from './studio/FieldEditorTable'
import { TemplateChat } from './template/TemplateChat'
import { TemplatePreview } from './template/TemplatePreview'
import { SampleAnalysisPanel } from './studio/SampleAnalysisPanel'
import { ComparisonSettingsPanel } from './studio/ComparisonSettingsPanel'
import { ExcelColumnEditor } from './studio/ExcelColumnEditor'

export interface ComparisonSettings {
    confidence_threshold: number; // 0.85
    ignore_position_changes: boolean; // true
    ignore_color_changes: boolean; // false
    ignore_font_changes: boolean; // true
    ignore_compression_noise: boolean; // true - JPEG artifacts
    custom_ignore_rules?: string; // custom instructions
    allowed_categories?: string[]; // Whitelist
    excluded_categories?: string[]; // Blacklist
    custom_categories?: { key: string; label: string; description: string }[]; // User defined
}

export interface ExcelExportColumn {
    key: string;
    label: string;
    width: number;
    enabled: boolean;
}

export interface ExtractionModel {
    id: string;
    name: string;
    description?: string;
    global_rules?: string;
    data_structure?: 'data' | 'table' | 'report'; // data=JSON, table=Grid
    model_type?: 'extraction' | 'comparison';
    azure_model_id?: string;
    webhook_url?: string;
    allowedGroups?: string[];
    fields: Field[];
    is_active: boolean;
    created_at?: string;
    updated_at?: string;
    // New Settings
    comparison_settings?: ComparisonSettings;
    excel_columns?: ExcelExportColumn[];
}

export function ModelStudio() {
    const { models, loading, saveModel, deleteModel, refineSchema } = useModels()
    const [editingModel, setEditingModel] = useState<Partial<Model> | null>(null)
    const [originalModel, setOriginalModel] = useState<Partial<Model> | null>(null)
    const [isEditing, setIsEditing] = useState(false)
    const [activeStudioTab, setActiveStudioTab] = useState<'extraction' | 'template'>('extraction')
    const [templateConfig, setTemplateConfig] = useState<Partial<TemplateConfig>>(defaultTemplateConfig)

    const handleNewModel = () => {
        setEditingModel(DEFAULTS.NEW_MODEL)
        setOriginalModel(null)
        setIsEditing(true)
    }

    const handleEditModel = (model: Model) => {
        setEditingModel({ ...model })
        setOriginalModel({ ...model })
        setIsEditing(false)
    }

    const handleSaveModel = async () => {
        if (!editingModel) return
        const result = await saveModel(editingModel)
        if (result.success && result.data) {
            toast.success(result.message)
            setIsEditing(false)
            setOriginalModel(result.data)
            setEditingModel(result.data)
        } else {
            toast.error(result.message)
        }
    }

    const handleCancelEdit = () => {
        if (originalModel) {
            setEditingModel(originalModel)
            setIsEditing(false)
        } else {
            setEditingModel(null)
        }
    }

    const handleDeleteModel = async (id: string) => {
        if (!window.confirm(MESSAGES.CONFIRM_DELETE)) return
        const result = await deleteModel(id)
        if (result.success) {
            toast.success('모델이 삭제되었습니다.')
        }
    }

    if (editingModel) {
        return (
            <div className="h-[calc(100vh-80px)] flex gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300 font-sans text-sm">
                {/* Main Editor Column */}
                <div className="flex-1 flex flex-col gap-3 overflow-hidden">
                    {/* Header */}
                    <header className="flex items-center justify-between shrink-0">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setEditingModel(null)}
                                className="p-1.5 bg-card hover:bg-accent text-muted-foreground hover:text-foreground rounded-lg shadow-sm border border-border transition-all active:scale-95"
                            >
                                <ArrowLeft className="w-3.5 h-3.5" />
                            </button>
                            <div className="flex flex-col">
                                <input
                                    type="text"
                                    value={editingModel.name}
                                    onChange={(e) => setEditingModel({ ...editingModel, name: e.target.value })}
                                    disabled={!isEditing}
                                    className={clsx(
                                        "text-lg font-black text-foreground bg-transparent border-none outline-none px-0",
                                        !isEditing && "cursor-default"
                                    )}
                                />
                                <span className="text-[10px] text-muted-foreground">
                                    {isEditing ? "편집 중" : "읽기 전용"}
                                </span>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {isEditing ? (
                                <>
                                    <Button variant="ghost" size="sm" onClick={handleCancelEdit}>
                                        취소
                                    </Button>
                                    <Button size="sm" onClick={handleSaveModel}>
                                        <Save className="w-3.5 h-3.5 mr-1" />
                                        저장
                                    </Button>
                                </>
                            ) : (
                                <Button size="sm" onClick={() => setIsEditing(true)}>
                                    <Edit className="w-3.5 h-3.5 mr-1" />
                                    편집
                                </Button>
                            )}
                        </div>
                    </header>

                    {/* Tabs */}
                    <div className="flex gap-1 bg-muted p-1 rounded-lg shrink-0">
                        <button
                            onClick={() => setActiveStudioTab('extraction')}
                            className={clsx(
                                "flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all",
                                activeStudioTab === 'extraction'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            📋 추출 설정
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('template')}
                            className={clsx(
                                "flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all",
                                activeStudioTab === 'template'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            🎨 템플릿
                        </button>
                    </div>

                    {/* Tab Content */}
                    {
                        activeStudioTab === 'extraction' && (
                            <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar pr-2">
                                {/* Sample Analysis Panel */}
                                {isEditing && (
                                    <SampleAnalysisPanel
                                        onFieldsFound={(foundFields) => {
                                            // Append new fields to existing ones
                                            // Check for duplicates? or just append?
                                            // Simple approach: Append and let user resolve
                                            const currentFields = editingModel.fields || []
                                            // Filter out duplicates based on key
                                            const newFields = foundFields.filter(f => !currentFields.some(curr => curr.key === f.key))

                                            setEditingModel({
                                                ...editingModel,
                                                fields: [...currentFields, ...newFields]
                                            })
                                        }}
                                        disabled={!isEditing}
                                    />
                                )}

                                {/* Natural Language Command Center with Gradient Border */}
                                <div className="relative p-[2px] rounded-xl bg-gradient-to-r from-primary via-chart-5 to-chart-3 animate-gradient-xy">
                                    <div className="bg-card rounded-xl p-6">
                                        <div className="flex items-center justify-between mb-4">
                                            <div className="flex items-center gap-2">
                                                <div className="bg-gradient-to-r from-primary to-chart-5 p-2 rounded-lg">
                                                    <Wand2 className="w-4 h-4 text-primary-foreground" />
                                                </div>
                                                <h3 className="font-bold text-base text-foreground">자연어 명령 센터</h3>
                                            </div>
                                            {isEditing && (
                                                <Button
                                                    size="sm"
                                                    onClick={async () => {
                                                        if (!editingModel.description) return
                                                        const result = await refineSchema(editingModel.fields || [], editingModel.description)
                                                        if (result && result.fields) {
                                                            setEditingModel({
                                                                ...editingModel,
                                                                fields: result.fields,
                                                                description: '' // Clear command after execution
                                                            })
                                                            toast.success('스키마가 수정되었습니다.')
                                                        }
                                                    }}
                                                    disabled={loading || !editingModel.description}
                                                    className="bg-primary hover:bg-primary/90"
                                                >
                                                    {loading ? (
                                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
                                                    ) : (
                                                        <Wand2 className="w-3.5 h-3.5 mr-1" />
                                                    )}
                                                    실행 (Execute)
                                                </Button>
                                            )}
                                        </div>
                                        <textarea
                                            value={editingModel.description}
                                            onChange={(e) => setEditingModel({ ...editingModel, description: e.target.value })}
                                            disabled={!isEditing}
                                            placeholder="예: '송장번호 키를 invoice_id로 바꾸고 타입 숫자로 변경해', '할인율 필드 제거해'..."
                                            className={clsx(
                                                "w-full h-24 px-4 py-3 text-sm border-2 border-primary/20 focus:border-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all resize-none bg-background",
                                                !isEditing && "bg-muted cursor-not-allowed"
                                            )}
                                        />
                                        <p className="mt-2 text-[10px] text-muted-foreground text-right">
                                            * 현재 필드들을 AI가 분석하여 명령을 수행합니다.
                                        </p>
                                    </div>
                                </div>

                                {/* Model Type Selection */}
                                <Card icon={Sliders} title="모델 유형">
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => setEditingModel({ ...editingModel, model_type: 'extraction' })}
                                            className={clsx(
                                                "flex-1 px-4 py-3 rounded-lg border-2 text-left transition-all",
                                                (!editingModel.model_type || editingModel.model_type === 'extraction')
                                                    ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                                                    : "border-border hover:border-primary/50 hover:bg-muted/50"
                                            )}
                                        >
                                            <div className="font-bold text-sm mb-1">📄 일반 추출 (Extraction)</div>
                                            <div className="text-xs text-muted-foreground">문서에서 텍스트와 데이터를 추출합니다.</div>
                                        </button>
                                        <button
                                            onClick={() => setEditingModel({ ...editingModel, model_type: 'comparison' })}
                                            className={clsx(
                                                "flex-1 px-4 py-3 rounded-lg border-2 text-left transition-all",
                                                editingModel.model_type === 'comparison'
                                                    ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                                                    : "border-border hover:border-primary/50 hover:bg-muted/50"
                                            )}
                                        >
                                            <div className="font-bold text-sm mb-1">⚖️ 비교 분석 (Comparison)</div>
                                            <div className="text-xs text-muted-foreground">두 이미지/문서 간의 차이점을 분석합니다.</div>
                                        </button>
                                    </div>
                                </Card>

                                {/* Extraction Fields - Only show for Extraction Models */}
                                {(!editingModel.model_type || editingModel.model_type === 'extraction') && (
                                    <Card icon={LayoutTemplate} title="추출 필드">
                                        <FieldEditorTable
                                            fields={editingModel.fields || []}
                                            onChange={(fields) => setEditingModel({ ...editingModel, fields })}
                                            disabled={!isEditing}
                                        />
                                        {isEditing && (
                                            <button
                                                onClick={() => {
                                                    const newField = { key: '', label: '', description: '', rules: '', type: 'string' as const }
                                                    setEditingModel({
                                                        ...editingModel,
                                                        fields: [...(editingModel.fields || []), newField]
                                                    })
                                                }}
                                                className="mt-3 w-full py-2 border-2 border-dashed border-border hover:border-primary text-muted-foreground hover:text-primary rounded-lg text-xs font-medium transition-all"
                                            >
                                                + 필드 추가
                                            </button>
                                        )}
                                    </Card>
                                )}

                                {/* Comparison Settings - Only show for Comparison Models */}
                                {editingModel.model_type === 'comparison' && (
                                    <>
                                        <ComparisonSettingsPanel
                                            settings={editingModel.comparison_settings}
                                            onChange={(settings) => setEditingModel({ ...editingModel, comparison_settings: settings })}
                                            disabled={!isEditing}
                                        />

                                        <ExcelColumnEditor
                                            columns={editingModel.excel_columns}
                                            onChange={(columns) => setEditingModel({ ...editingModel, excel_columns: columns })}
                                            disabled={!isEditing}
                                        />
                                    </>
                                )}

                                {/* Data Structure */}
                                <Card icon={RefreshCw} title="데이터 구조">
                                    <DataStructureSelector
                                        value={editingModel.data_structure || 'data'}
                                        onChange={(structure) => setEditingModel({ ...editingModel, data_structure: structure })}
                                        disabled={!isEditing}
                                    />
                                </Card>

                                {/* Advanced Settings */}
                                <Card icon={Sliders} title="고급 설정">
                                    <div className="mb-2 flex flex-wrap gap-2">
                                        {[
                                            "폰트 크기 및 스타일 차이 무시",
                                            "단순 텍스트 내용만 엄격하게 비교",
                                            "레이아웃 위치 변경은 허용",
                                            "이미지나 아이콘은 비교 제외",
                                            "로고 유무 필수 확인"
                                        ].map((rule) => (
                                            <button
                                                key={rule}
                                                onClick={() => {
                                                    const current = editingModel.global_rules || ""
                                                    const newValue = current ? `${current}\n- ${rule}` : `- ${rule}`
                                                    setEditingModel({ ...editingModel, global_rules: newValue })
                                                }}
                                                className="text-[10px] px-2 py-1 bg-primary/5 hover:bg-primary/10 text-primary border border-primary/20 rounded-full transition-colors"
                                            >
                                                + {rule}
                                            </button>
                                        ))}
                                    </div>
                                    <textarea
                                        value={editingModel.global_rules}
                                        onChange={(e) => setEditingModel({ ...editingModel, global_rules: e.target.value })}
                                        disabled={!isEditing}
                                        placeholder="전역 보정 규칙 또는 이미지 비교 규칙을 입력하세요... (예: '폰트 크기 차이 무시', '로고 유무 확인')"
                                        className={clsx(
                                            "w-full h-32 px-4 py-3 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all resize-none bg-background",
                                            !isEditing && "bg-muted cursor-not-allowed"
                                        )}
                                    />
                                    <p className="mt-1 text-[10px] text-muted-foreground flex justify-between">
                                        <span>추출 시에는 보정 규칙으로, 비교 시에는 차이점 판별 기준으로 사용됩니다.</span>
                                        <span className="text-primary cursor-pointer hover:underline" onClick={() => setEditingModel({ ...editingModel, global_rules: "" })}>초기화</span>
                                    </p>
                                    <div className="mt-4">
                                        <label className="block text-xs font-medium text-muted-foreground mb-2">
                                            🔗 Webhook URL (추출 완료 시 POST 전송)
                                        </label>
                                        <input
                                            type="url"
                                            value={editingModel.webhook_url || ''}
                                            onChange={(e) => setEditingModel({ ...editingModel, webhook_url: e.target.value })}
                                            disabled={!isEditing}
                                            placeholder="https://your-automation-endpoint.com/webhook"
                                            className={clsx(
                                                "w-full px-4 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all bg-background",
                                                !isEditing && "bg-muted cursor-not-allowed"
                                            )}
                                        />
                                        <p className="mt-1 text-[10px] text-muted-foreground">
                                            추출 확정 시 이 URL로 결과 데이터가 POST 됩니다.
                                        </p>
                                    </div>
                                </Card>
                            </div>
                        )
                    }

                    {/* Template Tab Content */}
                    {
                        activeStudioTab === 'template' && (
                            <div className="flex-1 flex gap-4 overflow-hidden">
                                {/* Left: Chat */}
                                <div className="w-[360px] shrink-0 h-full">
                                    <TemplateChat
                                        onConfigUpdate={(config) => setTemplateConfig(prev => ({ ...prev, ...config }))}
                                        modelFields={(editingModel.fields || []).map(f => ({
                                            key: f.key,
                                            label: f.label || f.key,
                                            type: f.type
                                        }))}
                                        currentConfig={templateConfig}
                                    />
                                </div>
                                {/* Right: Preview */}
                                <div className="flex-1">
                                    <TemplatePreview config={templateConfig} />
                                </div>
                            </div>
                        )
                    }
                </div>
            </div>
        )
    }

    // Gallery View - Pinterest Style
    return (
        <div className="h-[calc(100vh-80px)] p-6 font-sans overflow-y-auto custom-scrollbar">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-black text-foreground mb-1">모델 갤러리</h2>
                    <p className="text-sm text-muted-foreground">추출 모델을 생성하고 관리하세요</p>
                </div>
                <Button onClick={handleNewModel} className="gap-2">
                    <Plus className="w-4 h-4" />
                    새 모델 만들기
                </Button>
            </div>

            {loading ? (
                <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {models.map((model) => (
                        <div
                            key={model.id}
                            className="group cursor-pointer h-full"
                            onClick={() => handleEditModel(model)}
                        >
                            <div className="relative p-[2px] rounded-2xl bg-gradient-to-br from-border to-border hover:from-primary hover:to-chart-5 transition-all duration-300">
                                <div className="bg-card rounded-2xl p-5 h-full transition-all duration-300 group-hover:shadow-xl">
                                    <div className="flex items-start justify-between mb-3">
                                        <div className="bg-gradient-to-br from-primary/20 to-chart-5/20 p-2.5 rounded-xl group-hover:scale-110 transition-transform">
                                            <LayoutTemplate className="w-5 h-5 text-primary" />
                                        </div>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                handleDeleteModel(model.id)
                                            }}
                                            className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-destructive/10 rounded-lg transition-all"
                                        >
                                            <Trash2 className="w-4 h-4 text-destructive" />
                                        </button>
                                    </div>
                                    <h3 className="font-bold text-base text-foreground mb-2 group-hover:text-primary transition-colors">
                                        {model.name}
                                    </h3>
                                    <p className="text-xs text-muted-foreground mb-4 line-clamp-2">
                                        {model.description || '설명 없음'}
                                    </p>
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="text-muted-foreground">{model.fields?.length || 0}개 필드</span>
                                        <span className="px-2 py-1 bg-primary/10 text-primary rounded-full font-medium">
                                            {model.data_structure?.toUpperCase() || 'DATA'}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
