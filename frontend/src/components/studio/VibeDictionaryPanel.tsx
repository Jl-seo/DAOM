import { clsx } from 'clsx'
import { BookOpen, Sparkles, BrainCircuit, ShieldCheck, Info } from 'lucide-react'
import { Card } from '@/components/ui/icon-card'
import type { Model } from '../../types/model'

interface VibeDictionaryPanelProps {
    editingModel: Partial<Model>
    isEditing: boolean
    onUpdate: (model: Partial<Model>) => void
}

export function VibeDictionaryPanel({ editingModel, isEditing, onUpdate }: VibeDictionaryPanelProps) {
    if (editingModel.model_type && editingModel.model_type !== 'extraction') {
        return null;
    }

    const vibeConfig = editingModel.vibe_dictionary || {
        enabled: false,
        persona_prompt: '',
        target_fields: [],
        learning_mode: 'manual_approval' as const
    }

    const handleUpdate = (updates: Partial<typeof vibeConfig>) => {
        onUpdate({
            ...editingModel,
            vibe_dictionary: { ...vibeConfig, ...updates }
        })
    }

    return (
        <Card icon={BookOpen} title="AI 바이브 딕셔너리 (Vibe Dictionary) ─ 전문가 엔진">
            <div className="mb-6 p-4 rounded-xl bg-gradient-to-br from-indigo-500/5 to-blue-500/10 border border-indigo-500/20">
                <div className="flex items-start gap-4">
                    <div className="p-2.5 bg-indigo-500/20 rounded-lg shrink-0">
                        <BrainCircuit className="w-6 h-6 text-indigo-600" />
                    </div>
                    <div>
                        <h4 className="text-sm font-bold text-indigo-900 dark:text-indigo-300 mb-1">
                            지능형 오타 및 동의어 자동 보정 시스템 (Opt-out)
                        </h4>
                        <p className="text-xs text-indigo-800/80 dark:text-indigo-400/80 leading-relaxed mb-4">
                            추출 파이프라인(Phase 1) 직후, 모델 전용 AI 페르소나가 백그라운드에서 동작하여 추출된 텍스트 중 하드코딩된 규칙으로 잡지 못하는
                            휴먼 에러, нестандарт 축약어 등을 식별합니다. 식별된 내용은 사전(Dictionary)에 매핑되며, 향후 추출 시 자동으로 표준 값으로 치환됩니다.
                        </p>

                        <div className="flex items-center gap-6 mt-2 hidden sm:flex">
                            <StepBadge number={1} title="문서 추출" desc="OCR & LLM 파싱" />
                            <ArrowRight />
                            <StepBadge number={2} title="바이브 검수" desc="AI 페르소나 매핑" active />
                            <ArrowRight />
                            <StepBadge number={3} title="결과 반영" desc="사전 등록 및 치환" />
                        </div>
                    </div>
                </div>
            </div>

            <div className="space-y-6">
                <div className="flex items-center justify-between p-4 border border-border rounded-xl bg-card">
                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <Sparkles className="w-4 h-4 text-primary" />
                            <span className="text-sm font-bold text-foreground">엔진 활성화 (Vibe Engine Switch)</span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            활성화 시 배경에서 스크립트가 돌아가며 이 모델에 종속된 딕셔너리를 자동 구축합니다.
                        </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            className="sr-only peer"
                            checked={!!vibeConfig.enabled}
                            disabled={!isEditing}
                            onChange={() => handleUpdate({ enabled: !vibeConfig.enabled })}
                        />
                        <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-primary"></div>
                    </label>
                </div>

                {vibeConfig.enabled && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-in fade-in slide-in-from-top-4 duration-300">
                        {/* Left Column */}
                        <div className="space-y-6">
                            {/* Target Fields Section */}
                            <div className="bg-slate-50/50 dark:bg-secondary/10 p-5 rounded-xl border border-border/50">
                                <h5 className="flex items-center gap-2 text-xs font-bold text-foreground mb-3">
                                    <span className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary">1</span>
                                    학습 대상 필드 지정 (Target Fields)
                                </h5>
                                <p className="text-[11px] text-muted-foreground mb-4">
                                    추출된 데이터 중 AI가 오타나 약어를 검수할 항목을 선택하세요. (예: Port Code, Vendor Name)
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    {editingModel.fields?.map(f => {
                                        const isActive = vibeConfig.target_fields.includes(f.key)
                                        return (
                                            <button
                                                key={f.key}
                                                type="button"
                                                disabled={!isEditing}
                                                onClick={() => {
                                                    const current = vibeConfig.target_fields || []
                                                    const next = isActive ? current.filter(k => k !== f.key) : [...current, f.key]
                                                    handleUpdate({ target_fields: next })
                                                }}
                                                className={clsx(
                                                    "px-3 py-1.5 text-xs font-medium rounded-md border transition-all duration-200",
                                                    isActive
                                                        ? "bg-primary text-primary-foreground border-primary shadow-sm"
                                                        : "bg-background text-muted-foreground border-border hover:border-primary/50 hover:bg-primary/5"
                                                )}
                                            >
                                                {f.label} <span className="opacity-60 font-normal">({f.key})</span>
                                            </button>
                                        )
                                    })}
                                    {!(editingModel.fields?.length) && (
                                        <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-900/20 p-2 rounded w-full">
                                            <Info className="w-4 h-4" /> 추출 가이드에서 필드를 먼저 추가해주세요.
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Learning Mode Section */}
                            <div className="bg-slate-50/50 dark:bg-secondary/10 p-5 rounded-xl border border-border/50">
                                <h5 className="flex items-center gap-2 text-xs font-bold text-foreground mb-3">
                                    <span className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary">2</span>
                                    사전 반영 모드 (Learning Mode)
                                </h5>
                                <div className="space-y-3">
                                    <label className={clsx(
                                        "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                                        vibeConfig.learning_mode === 'auto_apply' ? "bg-primary/5 border-primary shadow-sm" : "bg-card border-border hover:border-primary/50"
                                    )}>
                                        <input
                                            type="radio"
                                            name="learning_mode"
                                            value="auto_apply"
                                            className="mt-1"
                                            checked={vibeConfig.learning_mode === 'auto_apply'}
                                            onChange={() => handleUpdate({ learning_mode: 'auto_apply' })}
                                            disabled={!isEditing}
                                        />
                                        <div>
                                            <p className="text-sm font-semibold text-foreground">완전 자동화 (Auto-Apply)</p>
                                            <p className="text-xs text-muted-foreground mt-0.5">AI가 식별한 동의어/오타 매핑을 즉시 마스터 사전에 반영하고 데이터에 적용합니다.</p>
                                        </div>
                                    </label>

                                    <label className={clsx(
                                        "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                                        vibeConfig.learning_mode === 'manual_approval' ? "bg-primary/5 border-primary shadow-sm" : "bg-card border-border hover:border-primary/50"
                                    )}>
                                        <input
                                            type="radio"
                                            name="learning_mode"
                                            value="manual_approval"
                                            className="mt-1"
                                            checked={vibeConfig.learning_mode === 'manual_approval'}
                                            onChange={() => handleUpdate({ learning_mode: 'manual_approval' })}
                                            disabled={!isEditing}
                                        />
                                        <div>
                                            <p className="text-sm font-semibold text-foreground">관리자 승인 필요 (Manual Approval)</p>
                                            <p className="text-xs text-muted-foreground mt-0.5">AI가 매핑을 제안하지만, 반영 전 관리자의 확인(Review) 절차를 거칩니다.</p>
                                        </div>
                                    </label>
                                </div>
                            </div>
                        </div>

                        {/* Right Column (Persona) */}
                        <div className="bg-slate-50/50 dark:bg-secondary/10 p-5 rounded-xl border border-border/50 h-full flex flex-col">
                            <h5 className="flex items-center gap-2 text-xs font-bold text-foreground mb-3">
                                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary">3</span>
                                AI 페르소나 설정 (System Prompt)
                            </h5>
                            <p className="text-[11px] text-muted-foreground mb-4">
                                오타를 검수할 AI의 배경지식과 역할을 정의하세요. 도메인 지식을 심어줄수록 정확도가 올라갑니다.
                            </p>

                            <div className="flex flex-wrap gap-2 mb-3">
                                <button
                                    type="button"
                                    disabled={!isEditing}
                                    onClick={() => handleUpdate({
                                        persona_prompt: "당신은 20년 차 글로벌 해운 물류 전문가입니다. INVOICE, B/L 등에 등장하는 항구명(POL/POD), 선사명 등의 축약어나 오타를 발견하면 UN/LOCODE와 같은 물류 표준 코드로 매핑해 주세요. 쓰레기 데이터는 무시하세요."
                                    })}
                                    className="text-[10px] px-2.5 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-700 dark:text-blue-400 font-medium border border-blue-500/20 rounded-md transition-colors"
                                >
                                    🚢 해운 물류 템플릿
                                </button>
                                <button
                                    type="button"
                                    disabled={!isEditing}
                                    onClick={() => handleUpdate({
                                        persona_prompt: "당신은 AP(Account Payable) 부서의 엄격한 재무 담당자입니다. 거래처명(Vendor), 결제조건(Payment Terms) 등에서 오타나 불규칙한 축약어를 발견하면 회사 내부 표준 거래처 코드로 매핑합니다. 숫자가 섞인 쓰레기 값은 매핑하지 마세요."
                                    })}
                                    className="text-[10px] px-2.5 py-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 font-medium border border-emerald-500/20 rounded-md transition-colors"
                                >
                                    💰 재무/회계 템플릿
                                </button>
                            </div>

                            <textarea
                                value={vibeConfig.persona_prompt || ""}
                                onChange={(e) => handleUpdate({ persona_prompt: e.target.value })}
                                disabled={!isEditing}
                                placeholder="예: 당신은 물류 담당자입니다..."
                                className={clsx(
                                    "flex-1 w-full min-h-[150px] px-4 py-3 text-sm font-mono border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all resize-none bg-background leading-relaxed",
                                    !isEditing && "bg-muted cursor-not-allowed"
                                )}
                            />

                            <div className="mt-4 p-3 bg-primary/5 border border-primary/20 rounded-lg flex gap-3">
                                <ShieldCheck className="w-5 h-5 text-primary shrink-0" />
                                <p className="text-[11px] text-muted-foreground leading-relaxed">
                                    <strong>보안(Security):</strong> 바이브 딕셔너리에 입력되는 원본 데이터는 학습용으로 저장되지 않는 Enterprise LLM 환경 (Azure OpenAI)에서만 안전하게 추론됩니다.
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </Card>
    )
}

function StepBadge({ number, title, desc, active = false }: { number: number, title: string, desc: string, active?: boolean }) {
    return (
        <div className={clsx(
            "flex items-center gap-2 p-2 rounded-lg border",
            active ? "bg-white dark:bg-slate-800 border-indigo-200 shadow-sm" : "bg-transparent border-transparent opacity-60"
        )}>
            <div className={clsx(
                "flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold",
                active ? "bg-indigo-500 text-white" : "bg-slate-200 text-slate-500"
            )}>
                {number}
            </div>
            <div>
                <p className={clsx("text-xs font-bold", active ? "text-indigo-900 dark:text-indigo-300" : "text-slate-600 dark:text-slate-400")}>{title}</p>
                <p className="text-[10px] text-slate-500">{desc}</p>
            </div>
        </div>
    )
}

function ArrowRight() {
    return (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-slate-400">
            <path d="M3.33331 8H12.6666" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M8 3.33331L12.6667 7.99998L8 12.6666" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}
