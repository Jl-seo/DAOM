import { clsx } from 'clsx'
import { Sliders, BookOpen } from 'lucide-react'
import { toast } from 'sonner'
import { Card } from '@/components/ui/icon-card'
import { ComparisonSettingsPanel } from './ComparisonSettingsPanel'
import { ExcelColumnEditor } from './ExcelColumnEditor'
import type { Model } from '../../types/model'

interface ModelSettingsTabProps {
    editingModel: Partial<Model>
    isEditing: boolean
    llmOptions: string[]
    onUpdate: (model: Partial<Model>) => void
    onSaveModel: (model: Partial<Model>) => Promise<{ success: boolean; data?: Model | null; message: string }>
}

export function ModelSettingsTab({
    editingModel,
    isEditing,
    llmOptions,
    onUpdate,
    onSaveModel,
}: ModelSettingsTabProps) {
    return (
        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
            {/* Model Type Selection */}
            <Card icon={Sliders} title="모델 유형">
                <div className="flex gap-2">
                    <button
                        onClick={() => onUpdate({ ...editingModel, model_type: 'extraction' })}
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
                        onClick={() => onUpdate({ ...editingModel, model_type: 'comparison' })}
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

            {/* Comparison Settings - Only show for Comparison Models */}
            {editingModel.model_type === 'comparison' && (
                <>
                    <ComparisonSettingsPanel
                        settings={editingModel.comparison_settings}
                        onChange={(settings) => onUpdate({ ...editingModel, comparison_settings: settings })}
                        disabled={!isEditing}
                    />

                    <ExcelColumnEditor
                        columns={editingModel.excel_columns}
                        onChange={(columns) => onUpdate({ ...editingModel, excel_columns: columns })}
                        disabled={!isEditing}
                    />
                </>
            )}

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
                                onUpdate({ ...editingModel, global_rules: newValue })
                            }}
                            className="text-[10px] px-2 py-1 bg-primary/5 hover:bg-primary/10 text-primary border border-primary/20 rounded-full transition-colors"
                        >
                            + {rule}
                        </button>
                    ))}
                </div>
                <textarea
                    value={editingModel.global_rules}
                    onChange={(e) => onUpdate({ ...editingModel, global_rules: e.target.value })}
                    disabled={!isEditing}
                    placeholder="전역 보정 규칙 또는 이미지 비교 규칙을 입력하세요... (예: '폰트 크기 차이 무시', '로고 유무 확인')"
                    className={clsx(
                        "w-full h-32 px-4 py-3 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all resize-none bg-background",
                        !isEditing && "bg-muted cursor-not-allowed"
                    )}
                />
                <p className="mt-1 text-[10px] text-muted-foreground flex justify-between">
                    <span>추출 시에는 보정 규칙으로, 비교 시에는 차이점 판별 기준으로 사용됩니다.</span>
                    <span className="text-primary cursor-pointer hover:underline" onClick={() => onUpdate({ ...editingModel, global_rules: "" })}>초기화</span>
                </p>
                <div className="mt-4">
                    <label className="block text-xs font-medium text-muted-foreground mb-2">
                        🔗 Webhook URL (추출 완료 시 POST 전송)
                    </label>
                    <input
                        type="url"
                        value={editingModel.webhook_url || ''}
                        onChange={(e) => onUpdate({ ...editingModel, webhook_url: e.target.value })}
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

                <div className="mt-4 pt-4 border-t border-border grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-2">
                            🤖 전처리 특화 LLM (선택)
                        </label>
                        <select
                            value={editingModel.mapper_llm || ''}
                            onChange={(e) => onUpdate({ ...editingModel, mapper_llm: e.target.value })}
                            disabled={!isEditing}
                            className={clsx(
                                "w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all bg-background appearance-none",
                                !isEditing && "bg-muted cursor-not-allowed"
                            )}
                        >
                            <option value="">(기본 모델 사용)</option>
                            {llmOptions.map(opt => (
                                <option key={opt} value={opt}>{opt}</option>
                            ))}
                        </select>
                        <p className="mt-1 text-[10px] text-muted-foreground">
                            헤더 평탄화 등 구조적 전처리에 사용할 빠르고 저렴한 모델 배포명.
                        </p>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-2">
                            🧠 주 추출 본 LLM (선택)
                        </label>
                        <select
                            value={editingModel.extractor_llm || ''}
                            onChange={(e) => onUpdate({ ...editingModel, extractor_llm: e.target.value })}
                            disabled={!isEditing}
                            className={clsx(
                                "w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all bg-background appearance-none",
                                !isEditing && "bg-muted cursor-not-allowed"
                            )}
                        >
                            <option value="">(기본 모델 사용)</option>
                            {llmOptions.map(opt => (
                                <option key={opt} value={opt}>{opt}</option>
                            ))}
                        </select>
                        <p className="mt-1 text-[10px] text-muted-foreground">
                            데이터를 최종 추출/보정할 메인 모델 배포명. (비워두면 환경변수의 기본 모델 사용)
                        </p>
                    </div>
                </div>

                {/* Beta Features - Only for extraction models */}
                {(!editingModel.model_type || editingModel.model_type === 'extraction') && (
                    <div className="mt-4 pt-4 border-t border-border">
                        <BetaToggle
                            label="🚀 [Beta] 최적화 프롬프트 사용"
                            badge={{ text: "BETA", color: "indigo" }}
                            description="OCR 위치 좌표를 제외하고 인덱스 태그로 참조하여 토큰 비용을 절감하고 복잡한 문서 인식률을 향상시킵니다."
                            enabled={!!editingModel.beta_features?.use_optimized_prompt}
                            disabled={!isEditing}
                            activeColor="bg-indigo-500"
                            onToggle={() => onUpdate({
                                ...editingModel,
                                beta_features: {
                                    ...editingModel.beta_features,
                                    use_optimized_prompt: !editingModel.beta_features?.use_optimized_prompt
                                }
                            })}
                        />

                        <BetaToggle
                            label="📊 가상 Excel OCR"
                            description="Excel/CSV 파일을 Azure OCR 없이 직접 파싱하여 비용을 절감합니다."
                            enabled={!!editingModel.beta_features?.use_virtual_excel_ocr}
                            disabled={!isEditing}
                            activeColor="bg-emerald-500"
                            onToggle={() => onUpdate({
                                ...editingModel,
                                beta_features: {
                                    ...editingModel.beta_features,
                                    use_virtual_excel_ocr: !editingModel.beta_features?.use_virtual_excel_ocr
                                }
                            })}
                        />

                        <BetaToggle
                            label="👁️ [Beta] Vision 추출 모드"
                            badge={{ text: "VISION", color: "amber" }}
                            description="3D 물체, 곡면 라벨 등 OCR이 어려운 이미지에 GPT-4.1 Vision을 사용하여 직접 추출합니다."
                            enabled={!!editingModel.beta_features?.use_vision_extraction}
                            disabled={!isEditing}
                            activeColor="bg-amber-500"
                            id="toggle-vision-extraction"
                            onToggle={() => onUpdate({
                                ...editingModel,
                                beta_features: {
                                    ...editingModel.beta_features,
                                    use_vision_extraction: !editingModel.beta_features?.use_vision_extraction
                                }
                            })}
                        />

                        <BetaToggle
                            label="⚡ [Beta] DEX 실시간 검증 (바코드)"
                            badge={{ text: "SCAN", color: "blue" }}
                            description="바코드 스캔 후 환자 성명을 즉시 수기 인식(OCR)하여 LIS 데이터와 실시간으로 교차 검증합니다."
                            enabled={!!editingModel.beta_features?.use_dex_validation}
                            disabled={!isEditing}
                            activeColor="bg-blue-600"
                            id="toggle-dex-validation"
                            className="mt-3 pt-3 border-t border-border/50"
                            onToggle={() => onUpdate({
                                ...editingModel,
                                beta_features: {
                                    ...editingModel.beta_features,
                                    use_dex_validation: !editingModel.beta_features?.use_dex_validation
                                }
                            })}
                        />
                    </div>
                )}
            </Card>

            {/* AI Vibe Dictionary Section */}
            {(!editingModel.model_type || editingModel.model_type === 'extraction') && (
                <Card icon={BookOpen} title="AI 바이브 딕셔너리 (Vibe Dictionary)">
                    <p className="text-xs text-muted-foreground mb-4">
                        추출 엔진이 일차적으로 데이터를 뽑은 후, 이 모델만의 독립적인 AI 페르소나가 백그라운드에서 오타와 동의어를 학습하여 자동 치환(Opt-out)합니다.
                    </p>

                    <div className="space-y-4">
                        <BetaToggle
                            label="✨ 바이브 딕셔너리 활성화 (Opt-out 비동기 검수)"
                            description="활성화 시 추출 완료 직후 AI가 기준 데이터를 기반으로 새로운 코드를 자동 학습합니다."
                            enabled={!!editingModel.vibe_dictionary?.enabled}
                            disabled={!isEditing}
                            activeColor="bg-primary"
                            onToggle={() => onUpdate({
                                ...editingModel,
                                vibe_dictionary: {
                                    ...editingModel.vibe_dictionary,
                                    enabled: !editingModel.vibe_dictionary?.enabled,
                                    persona_prompt: editingModel.vibe_dictionary?.persona_prompt || '',
                                    target_fields: editingModel.vibe_dictionary?.target_fields || []
                                }
                            })}
                        />

                        {editingModel.vibe_dictionary?.enabled && (
                            <div className="pl-4 border-l-2 border-border mt-4 space-y-4">
                                <div>
                                    <label className="block text-xs font-medium text-foreground mb-2">
                                        🎯 학습 대상 필드 지정 (Target Fields)
                                    </label>
                                    <div className="flex flex-wrap gap-2">
                                        {editingModel.fields?.map(f => {
                                            const isActive = editingModel.vibe_dictionary?.target_fields.includes(f.key)
                                            return (
                                                <button
                                                    key={f.key}
                                                    type="button"
                                                    disabled={!isEditing}
                                                    onClick={() => {
                                                        const current = editingModel.vibe_dictionary?.target_fields || []
                                                        const next = isActive ? current.filter(k => k !== f.key) : [...current, f.key]
                                                        onUpdate({
                                                            ...editingModel,
                                                            vibe_dictionary: { ...editingModel.vibe_dictionary!, target_fields: next }
                                                        })
                                                    }}
                                                    className={clsx(
                                                        "px-2 py-1 text-[10px] rounded border transition-colors",
                                                        isActive
                                                            ? "bg-primary text-primary-foreground border-primary"
                                                            : "bg-background text-muted-foreground border-border hover:border-primary/50"
                                                    )}
                                                >
                                                    {f.label} ({f.key})
                                                </button>
                                            )
                                        })}
                                        {!(editingModel.fields?.length) && (
                                            <span className="text-[10px] text-muted-foreground">필드를 먼저 추가해주세요.</span>
                                        )}
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-foreground mb-2 flex justify-between">
                                        <span>🤖 페르소나 프롬프트 (Persona)</span>
                                    </label>
                                    <div className="mb-2 flex flex-wrap gap-2">
                                        <button
                                            type="button"
                                            disabled={!isEditing}
                                            onClick={() => onUpdate({
                                                ...editingModel,
                                                vibe_dictionary: {
                                                    ...editingModel.vibe_dictionary!,
                                                    persona_prompt: "당신은 20년 차 글로벌 해운 물류 전문가입니다. INVOICE, B/L 등에 등장하는 항구명(POL/POD), 선사명 등의 축약어나 오타를 발견하면 UN/LOCODE와 같은 물류 표준 코드로 매핑해 주세요. 쓰레기 데이터는 무시하세요."
                                                }
                                            })}
                                            className="text-[10px] px-2 py-1 bg-blue-500/10 hover:bg-blue-500/20 text-blue-600 border border-blue-500/20 rounded transition-colors"
                                        >
                                            🚢 해운 물류 전문가 프리셋
                                        </button>
                                        <button
                                            type="button"
                                            disabled={!isEditing}
                                            onClick={() => onUpdate({
                                                ...editingModel,
                                                vibe_dictionary: {
                                                    ...editingModel.vibe_dictionary!,
                                                    persona_prompt: "당신은 AP(Account Payable) 부서의 엄격한 재무 담당자입니다. 거래처명(Vendor), 결제조건(Payment Terms) 등에서 오타나 불규칙한 축약어를 발견하면 회사 내부 표준 거래처 코드로 매핑합니다. 숫자가 섞인 쓰레기 값은 매핑하지 마세요."
                                                }
                                            })}
                                            className="text-[10px] px-2 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 border border-emerald-500/20 rounded transition-colors"
                                        >
                                            💰 재무 담당자 프리셋
                                        </button>
                                    </div>
                                    <textarea
                                        value={editingModel.vibe_dictionary?.persona_prompt || ""}
                                        onChange={(e) => onUpdate({
                                            ...editingModel,
                                            vibe_dictionary: { ...editingModel.vibe_dictionary!, persona_prompt: e.target.value }
                                        })}
                                        disabled={!isEditing}
                                        placeholder="이 모델의 딕셔너리가 학습할 때 AI가 가지게 될 역할(페르소나)과 주의사항을 적어주세요..."
                                        className={clsx(
                                            "w-full h-24 px-4 py-3 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary transition-all resize-none bg-background",
                                            !isEditing && "bg-muted cursor-not-allowed"
                                        )}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            )}

            {/* 모델 활성화/비활성화 토글 */}
            <Card icon={Sliders} title="시스템 상태">
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
                            onUpdate(updated)
                            // Immediately save to backend
                            if (editingModel.id) {
                                const result = await onSaveModel({ ...updated })
                                if (result.success) {
                                    toast.success(newActive ? '메뉴에 표시됩니다' : '메뉴에서 숨겨집니다', { duration: 1500 })
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
            </Card>
        </div>
    )
}


// ── Reusable Beta Toggle Component ──

interface BetaToggleProps {
    label: string
    description: string
    enabled: boolean
    disabled: boolean
    activeColor: string
    onToggle: () => void
    badge?: { text: string; color: string }
    id?: string
    className?: string
}

function BetaToggle({ label, description, enabled, disabled, activeColor, onToggle, badge, id, className }: BetaToggleProps) {
    const badgeColors: Record<string, string> = {
        indigo: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
        amber: "bg-amber-500/10 text-amber-600 border-amber-500/20",
        blue: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    }

    return (
        <div className={clsx("flex items-center justify-between", className || "mt-3")}>
            <div>
                <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-foreground">{label}</span>
                    {badge && (
                        <span className={clsx("px-1.5 py-0.5 rounded text-[10px] font-bold border", badgeColors[badge.color] || badgeColors.indigo)}>
                            {badge.text}
                        </span>
                    )}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[300px]">
                    {description}
                </p>
            </div>
            <button
                type="button"
                id={id}
                disabled={disabled}
                onClick={onToggle}
                className={clsx(
                    "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                    enabled ? activeColor : "bg-muted-foreground/30",
                    disabled && "opacity-50 cursor-not-allowed"
                )}
            >
                <span
                    className={clsx(
                        "inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm",
                        enabled ? "translate-x-6" : "translate-x-1"
                    )}
                />
            </button>
        </div>
    )
}
