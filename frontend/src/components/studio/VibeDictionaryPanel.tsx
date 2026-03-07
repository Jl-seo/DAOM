import { clsx } from 'clsx'
import { BookOpen } from 'lucide-react'
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

    return (
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
    )
}

function BetaToggle({ label, description, enabled, disabled, activeColor, onToggle, badge, id, className }: any) {
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
