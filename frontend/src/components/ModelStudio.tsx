import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
    Plus, Save, ArrowLeft, Wand2,
    Edit, Database, BookOpen, Settings2, FileText, TerminalSquare
} from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import { DEFAULTS, MESSAGES } from '../constants'
import { useModels } from '../hooks/useModels'
import { apiClient } from '../lib/api'
import type { Model, Field } from '../types/model'
import { Card } from '@/components/ui/icon-card'
import { Button } from '@/components/ui/button'
import { DexSettingsPanel } from './studio/DexSettingsPanel'
import { AdvancedSchemaEditor } from './studio/AdvancedSchemaEditor'
import { TransformationRulesEditor } from './studio/TransformationRulesEditor'
import { SampleAnalysisPanel } from './studio/SampleAnalysisPanel'
import { ReferenceDataEditor } from './studio/ReferenceDataEditor'
import { DictionaryPanel } from './studio/DictionaryPanel'
import { SubFieldEditorModal } from './studio/SubFieldEditorModal'
import { ModelSettingsTab } from './studio/ModelSettingsTab'
import { VibeDictionaryPanel } from './studio/VibeDictionaryPanel'
import { ModelGallery } from './studio/ModelGallery'

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
    mapper_llm?: string;
    extractor_llm?: string;
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
    const { models, loading, saveModel, deleteModel, refineSchema, fetchModels, fetchLlmOptions } = useModels()
    const [editingModel, setEditingModel] = useState<Partial<Model> | null>(null)
    const [originalModel, setOriginalModel] = useState<Partial<Model> | null>(null)
    const [isEditing, setIsEditing] = useState(false)
    const [activeStudioTab, setActiveStudioTab] = useState<'settings' | 'schema' | 'reference' | 'transformation'>('settings')
    const [llmOptions, setLlmOptions] = useState<string[]>([])
    const [globalDictionaries, setGlobalDictionaries] = useState<string[]>([])

    const [searchQuery, setSearchQuery] = useState('')
    const [searchParams, setSearchParams] = useSearchParams()
    const navigate = useNavigate()

    // Sub-field modal state
    const [subFieldModalOpen, setSubFieldModalOpen] = useState(false)
    const [selectedParentField, setSelectedParentField] = useState<{ index: number, field: Field } | null>(null)

    // Fetch LLM options for the dropdowns
    useEffect(() => {
        const loadLlmOptions = async () => {
            const options = await fetchLlmOptions()
            setLlmOptions(options)
        }
        loadLlmOptions()
    }, [fetchLlmOptions])

    // Fetch dictionary categories for the current model
    useEffect(() => {
        const loadDictionaries = async () => {
            if (!editingModel?.id) {
                setGlobalDictionaries([])
                return
            }
            try {
                const res = await apiClient.get('/dictionaries/categories', { params: { model_id: editingModel.id } })
                if (res.data?.categories) {
                    setGlobalDictionaries(res.data.categories.map((c: any) => c.category))
                }
            } catch (e) {
                console.error('Failed to load model dictionaries', e)
            }
        }
        loadDictionaries()
    }, [editingModel?.id])

    // Listen for custom event from FieldEditorTable to open SubField Modal
    useEffect(() => {
        const handleOpenSubFieldModal = (e: Event) => {
            const customEvent = e as CustomEvent<{ index: number, field: Field }>;
            setSelectedParentField(customEvent.detail);
            setSubFieldModalOpen(true);
        };
        window.addEventListener('open-subfield-modal', handleOpenSubFieldModal);
        return () => window.removeEventListener('open-subfield-modal', handleOpenSubFieldModal);
    }, []);

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

        // Auto-compute the required dictionaries array for back-end LLM processing based on field assignments
        const dictSet = new Set<string>();
        editingModel.fields?.forEach(f => {
            if (f.dictionary) dictSet.add(f.dictionary);
            f.sub_fields?.forEach(sf => {
                if (sf.dictionary) dictSet.add(sf.dictionary);
            });
        });
        const modelToSave = {
            ...editingModel,
            dictionaries: Array.from(dictSet)
        };

        const result = await saveModel(modelToSave)
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
                    <div className="flex gap-1 bg-muted p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar">
                        <button
                            onClick={() => setActiveStudioTab('settings')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'settings'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Settings2 className="w-4 h-4" /> 모델 전역 설정
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('schema')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'schema'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <FileText className="w-4 h-4" /> 추출 스키마
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('reference')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'reference'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Database className="w-4 h-4" /> 데이터 & 딕셔너리
                        </button>
                        {editingModel?.id && (
                            <button
                                onClick={() => setActiveStudioTab('transformation')}
                                className={clsx(
                                    "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                    activeStudioTab === 'transformation'
                                        ? "bg-card text-foreground shadow-sm"
                                        : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <TerminalSquare className="w-4 h-4" /> 후처리 스크립트
                            </button>
                        )}
                    </div>


                    {/* Schema Tab Content */}
                    {activeStudioTab === 'schema' && (
                        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
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

                            {/* Data Structure — DEPRECATED: auto-detected from field types
                                <Card icon={RefreshCw} title="데이터 구조">
                                    <DataStructureSelector
                                        value={editingModel.data_structure || 'data'}
                                        onChange={(structure) => setEditingModel({ ...editingModel, data_structure: structure })}
                                        disabled={!isEditing}
                                    />
                                </Card>
                                */}

                            <div className="mt-4 flex flex-col gap-3">
                                <div className="flex items-center gap-2 px-1">
                                    <div className="w-1 h-4 bg-primary rounded-full"></div>
                                    <h3 className="font-bold text-lg tracking-tight">추출 구조 설정</h3>
                                </div>
                                <AdvancedSchemaEditor
                                    fields={editingModel.fields || []}
                                    modelDictionaries={globalDictionaries}
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
                                        className="w-full py-3 bg-card border-2 border-dashed border-border/60 hover:border-primary hover:bg-primary/5 text-muted-foreground hover:text-primary rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center gap-2"
                                    >
                                        <Plus className="w-4 h-4" />
                                        새 필드 조각 추가하기
                                    </button>
                                )}
                            </div>

                            {/* Sub-Field Editor UI (Dialog) */}
                            <SubFieldEditorModal
                                isOpen={subFieldModalOpen}
                                onClose={() => setSubFieldModalOpen(false)}
                                parentField={selectedParentField?.field || null}
                                modelDictionaries={globalDictionaries}
                                onSave={(subFields) => {
                                    if (selectedParentField === null || !isEditing) return;
                                    const newFields = [...(editingModel.fields || [])];
                                    newFields[selectedParentField.index] = {
                                        ...newFields[selectedParentField.index],
                                        sub_fields: subFields
                                    };
                                    setEditingModel({ ...editingModel, fields: newFields });
                                }}
                            />

                        </div>
                    )}
                    {/* Reference Tab Content */}
                    {activeStudioTab === 'reference' && (
                        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
                            {/* Reference Data (Phase 1) */}
                            <Card icon={Database} title="참고 데이터 (Reference Data)">
                                <ReferenceDataEditor
                                    value={editingModel.reference_data}
                                    onChange={(data) => setEditingModel({ ...editingModel, reference_data: data })}
                                    disabled={!isEditing}
                                />
                            </Card>

                            {/* Dictionary Engine */}
                            <Card icon={BookOpen} title="정규화 딕셔너리 연동">
                                <DictionaryPanel
                                    modelId={editingModel.id || ''}
                                    disabled={!isEditing || !editingModel.id}
                                />
                            </Card>

                            {/* Vibe Dictionary Configuration */}
                            <VibeDictionaryPanel
                                editingModel={editingModel}
                                isEditing={isEditing}
                                onUpdate={setEditingModel}
                            />

                        </div>
                    )}
                    {/* Settings Tab Content */}
                    {activeStudioTab === 'settings' && (
                        <ModelSettingsTab
                            editingModel={editingModel}
                            isEditing={isEditing}
                            llmOptions={llmOptions}
                            onUpdate={setEditingModel}
                            onSaveModel={saveModel}
                        />
                    )}


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
                </div >
            </div >
        )
    }

    // Gallery View - Pinterest Style
    return (
        <ModelGallery
            models={models}
            loading={loading}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onNewModel={handleNewModel}
            onEditModel={handleEditModel}
            onDeleteModel={handleDeleteModel}
        />
    )
}
