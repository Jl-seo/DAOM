/* eslint-disable @typescript-eslint/no-explicit-any */
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
    CheckCircle2, XCircle, AlertTriangle, Brain, Search, 
    FileText, Clock, Hash 
} from 'lucide-react'

interface ReasoningMapPanelProps {
    surveyResult: any
    judgeResult: any
    extractedData: Record<string, any>
}

function StatusIcon({ found }: { found: boolean }) {
    return found 
        ? <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" /> 
        : <XCircle className="w-4 h-4 text-red-400 shrink-0" />
}

function GapBadge({ expected, actual }: { expected: number; actual: number }) {
    const diff = expected - actual
    if (diff <= 0) {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <CheckCircle2 className="w-3 h-3" /> {actual}행 추출 완료
            </span>
        )
    }
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <AlertTriangle className="w-3 h-3" /> {actual}/{expected}행 ({diff}행 부족)
        </span>
    )
}

export function ReasoningMapPanel({ surveyResult, judgeResult, extractedData }: ReasoningMapPanelProps) {
    const pythonFacts = surveyResult?.python_facts
    const aiInterp = surveyResult?.ai_interpretation
    const allEntities = surveyResult?.all_entities || []
    const elapsed = surveyResult?.elapsed_seconds

    const fieldMapping = aiInterp?.field_mapping || {}
    const tableAnalysis = aiInterp?.table_analysis || {}
    const docType = aiInterp?.document_type || ''

    // Calculate gap for table fields
    const gapInfo: Record<string, { expected: number; actual: number; missing: string[] }> = {}
    for (const [fk, info] of Object.entries(tableAnalysis) as [string, any][]) {
        const expected = info?.estimated_output_rows || pythonFacts?.total_table_rows || 0
        // Find actual extracted rows
        let actual = 0
        for (const [key, val] of Object.entries(extractedData || {})) {
            if (key.startsWith('_')) continue
            const list = val?.value && Array.isArray(val.value) ? val.value : (Array.isArray(val) ? val : null)
            if (list) {
                actual = Math.max(actual, list.length)
            }
        }
        gapInfo[fk] = { expected, actual, missing: info?.all_destination_names || [] }
    }

    // Judge issues
    const judgeIssues = judgeResult?.issues || []
    const judgeVerdict = judgeResult?.verdict
    const surveyGap = judgeResult?._survey_gap

    const hasData = surveyResult || judgeResult

    if (!hasData) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2 p-12">
                <Brain className="w-12 h-12 opacity-30" />
                <p className="text-lg font-medium">추론 맵 데이터 없음</p>
                <p className="text-xs">Beta 기능(use_judge)을 활성화한 후 추출하면 문서 구조 분석 결과가 여기에 표시됩니다.</p>
            </div>
        )
    }

    return (
        <ScrollArea className="h-full">
            <div className="p-6 space-y-6 max-w-3xl">
                {/* Header */}
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                        <Brain className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-sm">Document Survey 추론 맵</h3>
                        <p className="text-xs text-muted-foreground">{docType || '문서 구조 분석 결과'}</p>
                    </div>
                    {elapsed && (
                        <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                            <Clock className="w-3 h-3" /> {elapsed}초
                        </span>
                    )}
                </div>

                {/* Python Facts */}
                {pythonFacts && (
                    <div className="rounded-lg border bg-slate-50/50 p-4">
                        <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Hash className="w-3.5 h-3.5" /> Python 확정적 분석 (LLM 0회)
                        </h4>
                        <div className="grid grid-cols-3 gap-4">
                            <div className="text-center">
                                <div className="text-2xl font-bold text-slate-900">{pythonFacts.total_table_rows}</div>
                                <div className="text-[10px] text-slate-500 mt-0.5">표 행 수</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold text-slate-900">{pythonFacts.num_tables}</div>
                                <div className="text-[10px] text-slate-500 mt-0.5">테이블 수</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold text-slate-900">{pythonFacts.total_unique_entities}</div>
                                <div className="text-[10px] text-slate-500 mt-0.5">엔티티 수</div>
                            </div>
                        </div>
                        {pythonFacts.tables?.map((t: any, i: number) => (
                            <div key={i} className="mt-3 pt-3 border-t border-slate-200">
                                <div className="text-xs font-medium text-slate-700 mb-1">
                                    Table {t.table_index + 1}: {t.data_rows}개 데이터 행
                                </div>
                                <div className="text-[10px] text-slate-500">
                                    Headers: {t.headers?.slice(0, 6).join(' | ')}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Field Mapping */}
                {Object.keys(fieldMapping).length > 0 && (
                    <div className="rounded-lg border p-4">
                        <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Search className="w-3.5 h-3.5" /> AI 필드 위치 탐색
                        </h4>
                        <div className="space-y-2">
                            {Object.entries(fieldMapping).map(([key, info]: [string, any]) => (
                                <div key={key} className="flex items-start gap-2 text-sm">
                                    <StatusIcon found={info?.found} />
                                    <div className="flex-1 min-w-0">
                                        <span className="font-mono text-xs font-medium">{key}</span>
                                        {info?.value_hint && (
                                            <span className="ml-2 text-xs text-blue-600 font-medium">
                                                → {String(info.value_hint).slice(0, 50)}
                                            </span>
                                        )}
                                        {info?.source && (
                                            <span className="ml-1 text-[10px] text-slate-400">({info.source})</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Table Analysis + Gap Check */}
                {Object.keys(tableAnalysis).length > 0 && (
                    <div className="rounded-lg border p-4">
                        <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <FileText className="w-3.5 h-3.5" /> 테이블 분석 & Gap Check
                        </h4>
                        {Object.entries(tableAnalysis).map(([fk, info]: [string, any]) => {
                            const gap = gapInfo[fk]
                            return (
                                <div key={fk} className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="font-mono text-xs font-medium">{fk || 'Basic_Rate_List'}</span>
                                        {gap && <GapBadge expected={gap.expected} actual={gap.actual} />}
                                    </div>
                                    {info?.header_rows_to_skip?.length > 0 && (
                                        <div className="text-xs text-slate-500">
                                            <span className="font-medium">Skip:</span> {info.header_rows_to_skip.join(', ')}
                                        </div>
                                    )}
                                    {info?.rows_to_exclude?.length > 0 && (
                                        <div className="text-xs text-slate-500">
                                            <span className="font-medium">Exclude:</span> {info.rows_to_exclude.join(', ')}
                                        </div>
                                    )}
                                    {info?.rows_needing_split?.length > 0 && (
                                        <div className="text-xs text-slate-500">
                                            <span className="font-medium">Split:</span> {info.rows_needing_split.join(', ')}
                                        </div>
                                    )}
                                    {info?.missing_risk_note && (
                                        <div className="text-xs text-amber-600 bg-amber-50 p-2 rounded">
                                            ⚠️ {info.missing_risk_note}
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                )}

                {/* Survey Gap (Python deterministic) */}
                {surveyGap && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                        <h4 className="text-xs font-semibold text-amber-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                            <AlertTriangle className="w-3.5 h-3.5" /> 누락 감지 (Python Gap Check)
                        </h4>
                        <div className="text-sm font-medium text-amber-900 mb-1">
                            {surveyGap.field}: {surveyGap.extracted_count}행 추출, {surveyGap.missing_count}개 엔티티 누락
                        </div>
                        <div className="flex flex-wrap gap-1 mt-2">
                            {surveyGap.missing_entities?.map((e: string) => (
                                <span key={e} className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-100 text-amber-800">
                                    {e}
                                </span>
                            ))}
                        </div>
                    </div>
                )}

                {/* Judge Result */}
                {judgeResult && (
                    <div className={`rounded-lg border p-4 ${judgeVerdict === 'pass' ? 'bg-green-50/50 border-green-200' : 'bg-red-50/50 border-red-200'}`}>
                        <h4 className="text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
                            {judgeVerdict === 'pass' 
                                ? <><CheckCircle2 className="w-3.5 h-3.5 text-green-600" /> <span className="text-green-700">Judge: PASS</span></>
                                : <><AlertTriangle className="w-3.5 h-3.5 text-red-600" /> <span className="text-red-700">Judge: FLAGGED ({judgeIssues.length} issues)</span></>
                            }
                        </h4>
                        {judgeIssues.length > 0 && (
                            <div className="space-y-1">
                                {judgeIssues.map((issue: any, i: number) => (
                                    <div key={i} className="text-xs flex items-start gap-2">
                                        <span className={`px-1.5 py-0.5 rounded font-mono text-[10px] ${
                                            issue.type === 'INCOMPLETE' ? 'bg-amber-100 text-amber-800' :
                                            issue.type === 'HALLUCINATION' ? 'bg-red-100 text-red-800' :
                                            'bg-slate-100 text-slate-700'
                                        }`}>
                                            {issue.type}
                                        </span>
                                        <span className="text-slate-600">{issue.field}: {issue.reason?.slice(0, 100)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* All Entities */}
                {allEntities.length > 0 && (
                    <details className="rounded-lg border p-4">
                        <summary className="text-xs font-semibold text-slate-600 cursor-pointer hover:text-slate-900">
                            문서 내 감지된 엔티티 ({allEntities.length}개)
                        </summary>
                        <div className="flex flex-wrap gap-1 mt-3">
                            {allEntities.map((e: string) => (
                                <span key={e} className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600">
                                    {e}
                                </span>
                            ))}
                        </div>
                    </details>
                )}
            </div>
        </ScrollArea>
    )
}
