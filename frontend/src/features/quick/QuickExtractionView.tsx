import { useState, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, X, Loader2, FileText, Camera } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { extractionApi } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import type { ExtractionJob } from '@/types/extraction'
import { toast } from 'sonner'

// Simple polling hook for job status
// This hook is not part of the QuickExtractionView component, it's a separate function.
// Assuming it's defined outside or in a separate file, but for the context of this
// change, I'll keep it as is, just fixing the syntax error (missing function name).
// Let's assume it's a custom hook named `useJobPolling` as used later.
function useJobPolling(jobId: string | null) { // Added function name
    return useQuery({
        queryKey: ['job', jobId],
        queryFn: async () => {
            if (!jobId) return null
            const res = await extractionApi.getJob(jobId)
            return res.data as ExtractionJob
        },
        enabled: !!jobId,
        refetchInterval: (query) => {
            const data = query.state.data
            if (!data) return 1000
            // Status codes: P100=pending, P200=processing, P300=analyzing
            // E100=error, S100=success, S200=confirmed
            const processingStatuses = ['P100', 'P200', 'P300', 'pending', 'processing', 'analyzing']
            if (processingStatuses.includes(data.status)) return 2000
            return false // Stop polling on success/error
        }
    })
}

export function QuickExtractionView() {
    const [file, setFile] = useState<File | null>(null)
    const [jobId, setJobId] = useState<string | null>(null)
    // const [error, setError] = useState<string | null>(null)

    // Polling
    const { data: job, isLoading: isJobLoading } = useJobPolling(jobId)

    const onDrop = async (acceptedFiles: File[]) => {
        const f = acceptedFiles[0]
        if (!f) return
        setFile(f)
        // setError(null)
        setJobId(null)

        // Auto start
        try {
            const res = await extractionApi.uploadFile("system-universal", f)
            setJobId(res.data.job_id)
        } catch (err) {
            console.error(err)
            // setError("업로드에 실패했습니다.")
            alert("업로드에 실패했습니다.") // Fallback
            setFile(null)
        }
    }

    const { getRootProps, getInputProps } = useDropzone({
        onDrop,
        accept: {
            'image/*': [],
            'application/pdf': []
        },
        maxFiles: 1
    })

    // Camera input ref for mobile
    const cameraInputRef = useRef<HTMLInputElement>(null)
    const handleCameraCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            onDrop([e.target.files[0]])
        }
    }

    const handleReset = () => {
        setFile(null)
        setJobId(null)
        // setError(null)
    }

    // --- Render Result ---
    const isProcessing = (status: string) => ['P100', 'P200', 'P300', 'pending', 'processing', 'analyzing'].includes(status)
    const isError = (status: string) => ['E100', 'E200', 'error', 'cancelled'].includes(status)
    const isSuccess = (status: string) => ['S100', 'S200', 'success', 'completed', 'confirmed'].includes(status)

    const renderResult = () => {
        if (!job) return null
        if (isProcessing(job.status)) {
            return (
                <div className="flex flex-col items-center justify-center p-12 text-center space-y-4">
                    <div className="relative">
                        <Loader2 className="w-16 h-16 animate-spin text-primary" />
                        <div className="absolute inset-0 flex items-center justify-center text-xs font-bold">{job.status === 'P300' || job.status === 'analyzing' ? 'AI' : 'OCR'}</div>
                    </div>
                    <h3 className="text-xl font-semibold">AI가 문서를 분석하고 있습니다...</h3>
                    <p className="text-muted-foreground">잠시만 기다려주세요.</p>
                    <Button
                        variant="destructive"
                        size="sm"
                        onClick={async () => {
                            if (!confirm('분석을 중단하시겠습니까?')) return;
                            try {
                                await extractionApi.cancelJob(jobId!); // jobId is guaranteed if job exists and we are polling
                                toast.success('분석이 취소되었습니다.');
                                setJobId(null); // Stop polling
                                setFile(null); // Return to upload
                            } catch {
                                toast.error('취소 실패');
                            }
                        }}
                        className="mt-4"
                    >
                        분석 중단
                    </Button>
                </div>
            )
        }

        if (isError(job.status) || (isSuccess(job.status) && job.error)) {
            return (
                <div className="p-8 text-center text-red-500 bg-red-50 rounded-lg">
                    <h3 className="text-lg font-bold">{job.status === 'cancelled' ? '분석 취소됨' : '분석 실패'}</h3>
                    <p>{job.error || "작업이 중단되었습니다."}</p>
                    <div className="flex justify-center gap-3 mt-4">
                        <Button variant="outline" onClick={handleReset}>다시 시도</Button>
                        <Button
                            variant="default"
                            className="bg-red-600 hover:bg-red-700"
                            onClick={async () => {
                                if (!confirm('정말로 기록을 삭제하시겠습니까?')) return;
                                try {
                                    // Use job.job_id since ExtractionJob uses job_id
                                    await extractionApi.deleteJob(job.job_id || jobId!);
                                    toast.success('삭제되었습니다.');
                                    handleReset();
                                } catch {
                                    toast.error('삭제 실패');
                                }
                            }}
                        >
                            기록 삭제
                        </Button>
                    </div>
                </div>
            )
        }

        if (isSuccess(job.status)) {
            // Universal extraction result is in preview_data.sub_documents[0].data.guide_extracted
            // Or handle legacy structure if extraction_service didn't update preview_data structure specifically for universal?
            // In universal mode, we saved it into sub_documents[0].data.guide_extracted inside extraction_service.

            const subDoc = job.preview_data?.sub_documents?.[0]
            
            // Fallbacks for legacy/quick structure where data might just be in preview_data.guide_extracted
            let data = {}
            if (subDoc) {
                data = subDoc.data?.guide_extracted || {}
            } else if (job.preview_data?.guide_extracted) {
                data = job.preview_data.guide_extracted
            }

            const keys = Object.keys(data)

            if (keys.length === 0) {
                return (
                    <div className="text-center p-8">
                        <p className="text-muted-foreground">추출된 데이터가 없습니다.</p>
                        <Button onClick={handleReset} className="mt-4">다른 파일 올리기</Button>
                    </div>
                )
            }

            // --- Responsive View ---
            return (
                <div className="space-y-6">
                    <div className="flex justify-between items-center">
                        <h3 className="text-lg font-bold flex items-center gap-2">
                            <span className="bg-green-100 text-green-700 px-2 py-1 rounded text-sm">완료</span>
                            추출 결과 ({keys.length}개 항목)
                        </h3>
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                onClick={async () => {
                                    if (!confirm('기록을 삭제하시겠습니까?')) return;
                                    try {
                                        await extractionApi.deleteJob(job.job_id); // Use job_id
                                        toast.success('삭제되었습니다.');
                                        handleReset();
                                    } catch {
                                        toast.error('삭제 실패');
                                    }
                                }}
                                size="sm"
                                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                                삭제
                            </Button>
                            <Button variant="outline" onClick={handleReset} size="sm">새로 하기</Button>
                        </div>
                    </div>

                    {/* Mobile: Card View */}
                    <div className="block md:hidden space-y-3">
                        {keys.map(key => {
                            const item = data[key]
                            return (
                                <Card key={key} className="overflow-hidden">
                                    <div className="bg-muted/30 px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider border-b flex justify-between">
                                        <span>{key}</span>
                                        <span className="text-[10px] bg-white px-1 rounded border">{item.type}</span>
                                    </div>
                                    <div className="p-4 font-medium break-all">
                                        {item.value?.toString() || <span className="text-gray-300 mx-1">-</span>}
                                    </div>
                                </Card>
                            )
                        })}
                    </div>

                    {/* Desktop: Table Grid */}
                    <div className="hidden md:block border rounded-lg overflow-hidden">
                        <table className="w-full text-sm">
                            <thead className="bg-muted/50">
                                <tr className="border-b">
                                    <th className="px-4 py-3 text-left font-medium w-1/3 text-muted-foreground text-xs uppercase">Field</th>
                                    <th className="px-4 py-3 text-left font-medium text-muted-foreground text-xs uppercase">Extracted Value</th>
                                    <th className="px-4 py-3 text-left font-medium w-24 text-muted-foreground text-xs uppercase">Type</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y bg-card">
                                {keys.map(key => {
                                    const item = data[key]
                                    return (
                                        <tr key={key} className="hover:bg-muted/5 transition-colors">
                                            <td className="px-4 py-3 font-medium text-foreground">{key}</td>
                                            <td className="px-4 py-3 text-foreground">{item.value?.toString() || '-'}</td>
                                            <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{item.type}</td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )
        }

        return null
    }

    // --- Render Upload ---
    if (!file) {
        return (
            <div className="h-full flex flex-col p-4 md:p-8 animate-in fade-in zoom-in-95 duration-300">
                <div className="mb-6">
                    <h1 className="text-2xl font-bold tracking-tight">빠른 추출 (Quick Extraction)</h1>
                    <p className="text-muted-foreground">모델 설정 없이 모든 문서를 즉시 분석합니다.</p>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center min-h-[400px] border-2 border-dashed rounded-xl bg-muted/5 hover:bg-muted/10 transition-colors relative group">
                    <div {...getRootProps()} className="absolute inset-0 z-10 cursor-pointer" />
                    <input {...getInputProps()} name="file-upload" id="file-upload" />

                    <div className="flex flex-col items-center space-y-4 text-center p-6">
                        <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
                            <Upload className="w-10 h-10 text-primary" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold mb-2">파일을 여기에 놓거나 클릭하세요</h3>
                            <p className="text-muted-foreground text-sm max-w-xs mx-auto mb-4">
                                JPG, PNG, PDF 지원. <br />
                                카메라 촬영 사진도 가능합니다.
                            </p>
                        </div>

                        {/* Mobile Camera Button (Hidden input trigger) */}
                        <div className="md:hidden">
                            <Button
                                size="lg"
                                className="w-full relative z-20 pointer-events-auto"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    cameraInputRef.current?.click()
                                }}
                            >
                                <Camera className="mr-2 h-5 w-5" /> 사진 찍기 / 보관함
                            </Button>
                            <input
                                type="file"
                                accept="image/*"
                                capture="environment"
                                className="hidden"
                                ref={cameraInputRef}
                                onChange={handleCameraCapture}
                                name="camera-input"
                                id="camera-input"
                            />
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="h-full flex flex-col p-4 md:p-8">
            <div className="mb-6 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">분석 결과</h1>
                    <p className="text-muted-foreground flex items-center gap-2 text-sm mt-1">
                        <FileText className="w-4 h-4" /> {file.name}
                    </p>
                </div>
                {/* If loading, don't show cancel? or show cancel? */}
                {!isJobLoading && (
                    <Button variant="ghost" onClick={handleReset}><X className="w-5 h-5" /></Button>
                )}
            </div>

            <div className="flex-1 overflow-auto rounded-xl border bg-card p-4 shadow-sm">
                {renderResult()}
            </div>
        </div>
    )
}
