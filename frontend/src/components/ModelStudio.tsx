import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
    Plus, Trash2, Save, ArrowLeft, Wand2,
    LayoutTemplate, Edit, Sliders, Database, BookOpen
} from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import { DEFAULTS, MESSAGES } from '../constants'
import { useModels } from '../hooks/useModels'
import type { Model, Field } from '../types/model'
import { Card } from '@/components/ui/icon-card'
import { Button } from '@/components/ui/button'
// import { DataStructureSelector } from './studio/DataStructureSelector' // DEPRECATED: auto-detected from field types
import { DexSettingsPanel } from './studio/DexSettingsPanel'
import { FieldEditorTable } from './studio/FieldEditorTable'
import { TransformationRulesEditor } from './studio/TransformationRulesEditor'
import { SampleAnalysisPanel } from './studio/SampleAnalysisPanel'
import { ComparisonSettingsPanel } from './studio/ComparisonSettingsPanel'
import { ExcelColumnEditor } from './studio/ExcelColumnEditor'
import { ReferenceDataEditor } from './studio/ReferenceDataEditor'
import { DictionaryPanel } from './studio/DictionaryPanel'

export interface ComparisonSettings {
    confidence_threshold: number; // 0.85
    ignore_position_changes: boolean; // true
    ignore_color_changes: boolean; // false
    ignore_font_changes: boolean; // true
    ignore_compression_noise: boolean; // true - JPEG artifacts
    custom_ignore_rules?: string; // custom instructions
    output_language?: string; // Korean
    // Method Toggles (Component-Based Architecture)
    use_ssim_analysis?: boolean; // true - Physical layer
    use_vision_analysis?: boolean; // false - Visual layer (requires Azure AI Vision)
    align_images?: boolean; // true - Image registration
    allowed_categories?: string[]; // Whitelist
    excluded_categories?: string[]; // Blacklist
    custom_categories?: { key: string; label: string; description: string }[]; // User defined
    ssim_identity_threshold?: number; // Global SSIM score gate (0.90~1.0, default 0.95)
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
    reference_data?: Record<string, unknown>;  // Phase 1: 참고 데이터
    dictionaries?: string[];  // Dictionary categories for auto-normalization
    transform_rules?: any[];  // Row expansion rules
}

export function ModelStudio() {
    const { models, loading, saveModel, deleteModel, refineSchema, fetchModels } = useModels()
    const [editingModel, setEditingModel] = useState<Partial<Model> | null>(null)
    const [originalModel, setOriginalModel] = useState<Partial<Model> | null>(null)
    const [isEditing, setIsEditing] = useState(false)
    const [activeStudioTab, setActiveStudioTab] = useState<'extraction' | 'transformation'>('extraction')
    const [searchParams, setSearchParams] = useSearchParams()
    const navigate = useNavigate()

    // Auto-select model from URL query param (e.g. ?modelId=xxx)
    useEffect(() => {
        const targetModelId = searchParams.get('modelId')

        // Force refresh models when entering Studio from another page
        if (targetModelId) {
            fetchModels()
        }

        if (targetModelId && models.length > 0 && !editingModel) {
            const found = models.find(m => m.id === targetModelId)
            if (found) {
                handleEditModel(found)
                // Clean up the query param so refresh doesn't re-trigger
                searchParams.delete('modelId')
                setSearchParams(searchParams, { replace: true })
            }
        }
    }, [models.length, searchParams]) // Listen to length to trigger after fetch completes

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
            toast.success(result.message, { duration: 1500 })
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
                                onClick={() => {
                                    if (searchParams.get('from') === 'extraction') {
                                        navigate(-1)
                                    } else {
                                        setEditingModel(null)
                                    }
                                }}
                                className="p-1.5 bg-card hover:bg-accent text-muted-foreground hover:text-foreground rounded-lg shadow-sm border border-border transition-all active:scale-95"
                                title={searchParams.get('from') === 'extraction' ? '추출 화면으로 돌아가기' : '목록으로 돌아가기'}
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
                            onClick={() => setActiveStudioTab('transformation')}
                            className={clsx(
                                "flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all",
                                activeStudioTab === 'transformation'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            🔄 변환 규칙 (Transformation)
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

                                {/* DEX Settings Panel — only visible when barcode feature is enabled */}
                                {(!editingModel.model_type || editingModel.model_type === 'extraction') && editingModel.beta_features?.use_dex_validation && (
                                    <DexSettingsPanel
                                        fields={editingModel.fields || []}
                                        onChange={(fields) => {
                                            const updated = { ...editingModel, fields }
                                            setEditingModel(updated)
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

                                {/* Data Structure — DEPRECATED: auto-detected from field types
                                <Card icon={RefreshCw} title="데이터 구조">
                                    <DataStructureSelector
                                        value={editingModel.data_structure || 'data'}
                                        onChange={(structure) => setEditingModel({ ...editingModel, data_structure: structure })}
                                        disabled={!isEditing}
                                    />
                                </Card>
                                */}

                                {/* Reference Data (Phase 1) */}
                                <Card icon={Database} title="참고 데이터 (Reference Data)">
                                    <ReferenceDataEditor
                                        value={editingModel.reference_data}
                                        onChange={(data) => setEditingModel({ ...editingModel, reference_data: data })}
                                        disabled={!isEditing}
                                    />
                                </Card>

                                {/* Dictionary Engine */}
                                <Card icon={BookOpen} title="딕셔너리 (Dictionary Engine)">
                                    <DictionaryPanel
                                        modelDictionaries={editingModel.dictionaries || []}
                                        onDictionariesChange={(dicts) => setEditingModel({ ...editingModel, dictionaries: dicts })}
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

                                    {/* Beta Features - Only for extraction models */}
                                    {(!editingModel.model_type || editingModel.model_type === 'extraction') && (
                                        <div className="mt-4 pt-4 border-t border-border">
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-medium text-foreground">🚀 [Beta] 최적화 프롬프트 사용</span>
                                                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/10 text-indigo-500 font-bold border border-indigo-500/20">BETA</span>
                                                    </div>
                                                    <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[300px]">
                                                        OCR 위치 좌표를 제외하고 인덱스 태그로 참조하여 토큰 비용을 절감하고 복잡한 문서 인식률을 향상시킵니다.
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    disabled={!isEditing}
                                                    onClick={() => setEditingModel({
                                                        ...editingModel,
                                                        beta_features: {
                                                            ...editingModel.beta_features,
                                                            use_optimized_prompt: !editingModel.beta_features?.use_optimized_prompt
                                                        }
                                                    })}
                                                    className={clsx(
                                                        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                                                        editingModel.beta_features?.use_optimized_prompt
                                                            ? "bg-indigo-500"
                                                            : "bg-muted-foreground/30",
                                                        !isEditing && "opacity-50 cursor-not-allowed"
                                                    )}
                                                >
                                                    <span
                                                        className={clsx(
                                                            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                                                            editingModel.beta_features?.use_optimized_prompt ? "translate-x-6" : "translate-x-1"
                                                        )}
                                                    />
                                                </button>
                                            </div>

                                            {/* Virtual Excel OCR Toggle */}
                                            <div className="flex items-center justify-between mt-3">
                                                <div>
                                                    <label className="block text-xs font-medium text-foreground">
                                                        📊 가상 Excel OCR
                                                    </label>
                                                    <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[300px]">
                                                        Excel/CSV 파일을 Azure OCR 없이 직접 파싱하여 비용을 절감합니다.
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    disabled={!isEditing}
                                                    onClick={() => setEditingModel({
                                                        ...editingModel,
                                                        beta_features: {
                                                            ...editingModel.beta_features,
                                                            use_virtual_excel_ocr: !editingModel.beta_features?.use_virtual_excel_ocr
                                                        }
                                                    })}
                                                    className={clsx(
                                                        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                                                        editingModel.beta_features?.use_virtual_excel_ocr
                                                            ? "bg-emerald-500"
                                                            : "bg-muted-foreground/30",
                                                        !isEditing && "opacity-50 cursor-not-allowed"
                                                    )}
                                                >
                                                    <span
                                                        className={clsx(
                                                            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                                                            editingModel.beta_features?.use_virtual_excel_ocr ? "translate-x-6" : "translate-x-1"
                                                        )}
                                                    />
                                                </button>
                                            </div>

                                            {/* Vision Extraction Toggle */}
                                            <div className="flex items-center justify-between mt-3">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-medium text-foreground">👁️ [Beta] Vision 추출 모드</span>
                                                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-600 font-bold border border-amber-500/20">VISION</span>
                                                    </div>
                                                    <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[300px]">
                                                        3D 물체, 곡면 라벨 등 OCR이 어려운 이미지에 GPT-4.1 Vision을 사용하여 직접 추출합니다.
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    id="toggle-vision-extraction"
                                                    disabled={!isEditing}
                                                    onClick={() => setEditingModel({
                                                        ...editingModel,
                                                        beta_features: {
                                                            ...editingModel.beta_features,
                                                            use_vision_extraction: !editingModel.beta_features?.use_vision_extraction
                                                        }
                                                    })}
                                                    className={clsx(
                                                        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                                                        editingModel.beta_features?.use_vision_extraction
                                                            ? "bg-amber-500"
                                                            : "bg-muted-foreground/30",
                                                        !isEditing && "opacity-50 cursor-not-allowed"
                                                    )}
                                                >
                                                    <span
                                                        className={clsx(
                                                            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                                                            editingModel.beta_features?.use_vision_extraction ? "translate-x-6" : "translate-x-1"
                                                        )}
                                                    />
                                                </button>
                                            </div>

                                            {/* DEX Validation Toggle */}
                                            <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/50">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-medium text-foreground">⚡ [Beta] DEX 실시간 검증 (바코드)</span>
                                                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-600 font-bold border border-blue-500/20">SCAN</span>
                                                    </div>
                                                    <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[300px]">
                                                        바코드 스캔 후 환자 성명을 즉시 수기 인식(OCR)하여 LIS 데이터와 실시간으로 교차 검증합니다.
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    id="toggle-dex-validation"
                                                    disabled={!isEditing}
                                                    onClick={() => setEditingModel({
                                                        ...editingModel,
                                                        beta_features: {
                                                            ...editingModel.beta_features,
                                                            use_dex_validation: !editingModel.beta_features?.use_dex_validation
                                                        }
                                                    })}
                                                    className={clsx(
                                                        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                                                        editingModel.beta_features?.use_dex_validation
                                                            ? "bg-blue-600"
                                                            : "bg-muted-foreground/30",
                                                        !isEditing && "opacity-50 cursor-not-allowed"
                                                    )}
                                                >
                                                    <span
                                                        className={clsx(
                                                            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                                                            editingModel.beta_features?.use_dex_validation ? "translate-x-6" : "translate-x-1"
                                                        )}
                                                    />
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* 모델 활성화/비활성화 토글 */}
                                    <div className="mt-4 pt-4 border-t border-border">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <label className="block text-xs font-medium text-foreground">
                                                    👁️ 메뉴에서 보이기
                                                </label>
                                                <p className="text-[10px] text-muted-foreground mt-0.5">
                                                    비활성화하면 사이드바 메뉴에서 숨겨집니다 (삭제되지 않음)
                                                </p>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={async () => {
                                                    const newActive = editingModel.is_active === false ? true : false
                                                    const updated = { ...editingModel, is_active: newActive }
                                                    setEditingModel(updated)
                                                    // Immediately save to backend
                                                    if (editingModel.id) {
                                                        const result = await saveModel({ ...updated })
                                                        if (result.success) {
                                                            toast.success(newActive ? '메뉴에 표시됩니다' : '메뉴에서 숨겨집니다', { duration: 1500 })
                                                            if (result.data) setOriginalModel(result.data)
                                                        }
                                                    }
                                                }}
                                                className={clsx(
                                                    "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                                                    editingModel.is_active !== false
                                                        ? "bg-primary"
                                                        : "bg-muted-foreground/30"
                                                )}
                                            >
                                                <span
                                                    className={clsx(
                                                        "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                                                        editingModel.is_active !== false ? "translate-x-6" : "translate-x-1"
                                                    )}
                                                />
                                            </button>
                                        </div>
                                    </div>
                                </Card>
                            </div>
                        )
                    }

                    {/* Transformation Rules Tab Content */}
                    {
                        activeStudioTab === 'transformation' && editingModel?.id && (
                            <div className="flex-1 h-full overflow-hidden">
                                <TransformationRulesEditor
                                    model={editingModel as Model}
                                    onUpdate={(updated) => setEditingModel(updated)}
                                />
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
                    <h2 className="text-2xl font-black text-foreground mb-1">모델 스튜디오</h2>
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
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {models.map((model) => (
                        <div
                            key={model.id}
                            className={clsx(
                                "group cursor-pointer h-full",
                                model.is_active === false && "opacity-60"
                            )}
                            onClick={() => handleEditModel(model)}
                        >
                            <div className={clsx(
                                "relative p-[2px] rounded-2xl transition-all duration-300",
                                model.is_active === false
                                    ? "bg-muted-foreground/30"
                                    : "bg-gradient-to-br from-border to-border hover:from-primary hover:to-chart-5"
                            )}>
                                <div className="bg-card rounded-2xl p-5 h-full transition-all duration-300 group-hover:shadow-xl">
                                    <div className="flex items-start justify-between mb-3">
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
                                        <div className="flex items-center gap-1">
                                            {model.is_active === false && (
                                                <span className="px-2 py-0.5 text-[10px] bg-muted-foreground/20 text-muted-foreground rounded-full">
                                                    숨김
                                                </span>
                                            )}
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
                                    </div>
                                    <h3 className={clsx(
                                        "font-bold text-base mb-2 transition-colors",
                                        model.is_active === false
                                            ? "text-muted-foreground"
                                            : "text-foreground group-hover:text-primary"
                                    )}>
                                        {model.name}
                                    </h3>
                                    <p className="text-xs text-muted-foreground mb-4 line-clamp-2">
                                        {model.description || '설명 없음'}
                                    </p>
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="text-muted-foreground">{model.fields?.length || 0}개 필드</span>
                                        <span className={clsx(
                                            "px-2 py-1 rounded-full font-medium",
                                            model.is_active === false
                                                ? "bg-muted-foreground/10 text-muted-foreground"
                                                : "bg-primary/10 text-primary"
                                        )}>
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
