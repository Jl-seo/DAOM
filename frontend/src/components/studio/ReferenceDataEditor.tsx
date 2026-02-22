/* eslint-disable react-hooks/exhaustive-deps */

import { useState, useEffect } from 'react'
import { AlertCircle, CheckCircle2, Database, HelpCircle } from 'lucide-react'
import { clsx } from 'clsx'

interface ReferenceDataEditorProps {
    value?: Record<string, unknown>
    onChange: (data: Record<string, unknown> | undefined) => void
    disabled?: boolean
}

const EXAMPLE_DATA = {
    customer_codes: {
        "UND001": "유니드 본사",
        "UND002": "유니드 물류센터",
        "SAM001": "삼성전자"
    },
    validation: {
        invoice_format: "INV-YYYYMMDD-NNN",
        currency: ["KRW", "USD", "EUR"]
    }
}

export function ReferenceDataEditor({ value, onChange, disabled }: ReferenceDataEditorProps) {
    const [jsonText, setJsonText] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isValid, setIsValid] = useState(true)

    // Initialize text from value
    useEffect(() => {
        if (value && Object.keys(value).length > 0) {
            setJsonText(JSON.stringify(value, null, 2))
            setIsValid(true)
            setError(null)
        } else {
            setJsonText('')
        }
    }, []) // Only on mount

    const handleChange = (text: string) => {
        setJsonText(text)

        if (!text.trim()) {
            setError(null)
            setIsValid(true)
            onChange(undefined)
            return
        }

        try {
            const parsed = JSON.parse(text)
            if (typeof parsed !== 'object' || Array.isArray(parsed)) {
                setError('JSON 객체 형식이어야 합니다 (배열 X)')
                setIsValid(false)
                return
            }
            setError(null)
            setIsValid(true)
            onChange(parsed)
        } catch {
            setError('유효하지 않은 JSON 형식입니다')
            setIsValid(false)
        }
    }

    const loadExample = () => {
        const exampleText = JSON.stringify(EXAMPLE_DATA, null, 2)
        setJsonText(exampleText)
        setError(null)
        setIsValid(true)
        onChange(EXAMPLE_DATA)
    }

    return (
        <div className="space-y-3">
            {/* Header with help */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Database className="w-4 h-4 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">
                        고객코드 매핑, 유효성 규칙 등 LLM이 참고할 데이터
                    </span>
                </div>
                {!disabled && (
                    <button
                        onClick={loadExample}
                        className="text-[10px] text-primary hover:underline flex items-center gap-1"
                    >
                        <HelpCircle className="w-3 h-3" />
                        예시 불러오기
                    </button>
                )}
            </div>

            {/* JSON Editor */}
            <div className="relative">
                <textarea
                    value={jsonText}
                    onChange={(e) => handleChange(e.target.value)}
                    disabled={disabled}
                    placeholder={`{
  "customer_codes": {
    "A001": "고객사 A",
    "B002": "고객사 B"
  },
  "validation": {
    "currency": ["KRW", "USD"]
  }
}`}
                    className={clsx(
                        "w-full h-48 px-4 py-3 font-mono text-xs border rounded-lg transition-all resize-none",
                        "focus:outline-none focus:ring-2",
                        disabled && "bg-muted cursor-not-allowed",
                        error
                            ? "border-destructive focus:ring-destructive/20 focus:border-destructive"
                            : isValid && jsonText
                                ? "border-green-500 focus:ring-green-500/20 focus:border-green-500"
                                : "border-border focus:ring-ring focus:border-primary"
                    )}
                />

                {/* Status indicator */}
                {jsonText && (
                    <div className="absolute top-2 right-2">
                        {error ? (
                            <AlertCircle className="w-4 h-4 text-destructive" />
                        ) : (
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                        )}
                    </div>
                )}
            </div>

            {/* Error message */}
            {error && (
                <p className="text-xs text-destructive flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {error}
                </p>
            )}

            {/* Help text */}
            <div className="text-[10px] text-muted-foreground space-y-2 mt-2">
                <div className="space-y-1">
                    <p>• <strong>customer_codes</strong>: 코드 → 이름 매핑 (예: 고객코드, 품목코드)</p>
                    <p>• <strong>validation</strong>: 유효값 목록, 형식 규칙 등</p>
                    <p>• 추출 시 LLM이 이 데이터를 참고하여 값을 변환하거나 검증합니다.</p>
                </div>

                <div className="p-2.5 bg-blue-50/50 border border-blue-100 rounded-md">
                    <p className="text-blue-800 font-medium flex items-center gap-1 mb-1">
                        <HelpCircle className="w-3 h-3" />
                        여러 데이터를 넣을 때 주의사항
                    </p>
                    <p className="text-blue-700/80 mb-1.5 leading-relaxed">
                        JSON 규칙상 <strong>동일한 키를 여러 번 쓰면 맨 마지막 1개만 저장</strong>됩니다. 여러 사람의 정보를 넣으려면 <strong>반드시 배열 <code>[ ]</code> 기호를 사용</strong>해주세요.
                    </p>
                    <div className="grid grid-cols-2 gap-2 text-[9px] font-mono">
                        <div className="bg-white p-1.5 rounded border border-red-100">
                            <span className="text-red-500 font-bold block mb-1">❌ 잘못된 예 (덮어쓰기 발생)</span>
                            {`{
  "고객정보": { "이름": "황양숙" },
  "고객정보": { "이름": "강수빈" }
}`}
                        </div>
                        <div className="bg-white p-1.5 rounded border border-green-100">
                            <span className="text-emerald-500 font-bold block mb-1">✅ 올바른 예 (배열 사용)</span>
                            {`{
  "고객목록": [
    { "이름": "황양숙" },
    { "이름": "강수빈" }
  ]
}`}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
