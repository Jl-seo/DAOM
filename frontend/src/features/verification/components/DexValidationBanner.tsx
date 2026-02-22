import { CheckCircle2, AlertTriangle, ScanLine } from 'lucide-react'
import { clsx } from 'clsx'

export interface DexValidationData {
    status: 'PASS' | 'FAIL'
    barcode: string
    target_field_key: string
    lis_expected_value: string
    llm_extracted_value: string
}

interface DexValidationBannerProps {
    data: DexValidationData
}

export function DexValidationBanner({ data }: DexValidationBannerProps) {
    const isPass = data.status === 'PASS'

    return (
        <div className={clsx(
            "flex items-start gap-4 p-4 rounded-lg border shadow-sm mb-6",
            isPass ? "bg-emerald-50/50 border-emerald-200" : "bg-destructive/5 border-destructive/20"
        )}>
            <div className={clsx(
                "p-2 rounded-full shrink-0",
                isPass ? "bg-emerald-100 text-emerald-600" : "bg-destructive/10 text-destructive"
            )}>
                {isPass ? (
                    <CheckCircle2 className="w-5 h-5" />
                ) : (
                    <AlertTriangle className="w-5 h-5" />
                )}
            </div>

            <div className="flex-1 min-w-0">
                <h3 className={clsx(
                    "text-sm font-semibold flex items-center mb-1",
                    isPass ? "text-emerald-800" : "text-destructive"
                )}>
                    {isPass ? 'DEX 검증 완료 (일치)' : 'DEX 검증 실패 (불일치 발생)'}
                    <span className="ml-3 px-2 py-0.5 rounded text-[10px] bg-slate-100 border text-slate-600 font-medium flex items-center w-fit">
                        <ScanLine className="w-3 h-3 mr-1" />
                        바코드: {data.barcode}
                    </span>
                </h3>

                <p className={clsx(
                    "text-sm leading-relaxed",
                    isPass ? "text-emerald-700/80" : "text-destructive/80"
                )}>
                    {isPass
                        ? `환자 LIS 정답("${data.lis_expected_value}")과 LLM 추출 결과("${data.llm_extracted_value}")가 스키마 타겟 '${data.target_field_key}' 에서 교차 검증 되었습니다.`
                        : `환자 LIS 정답은 "${data.lis_expected_value}" 이지만, LLM은 "${data.llm_extracted_value}" 로 판독했습니다. 추출본을 확인하고 수정해주세요.`
                    }
                </p>
            </div>
        </div>
    )
}
