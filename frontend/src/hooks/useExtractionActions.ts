/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * useExtractionActions - Consolidated hook for extraction log actions
 * Handles retry, download, delete, cancel operations
 */
// Forced redeploy: 2026-01-06 09:30
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient, extractionApi } from '@/lib/api'
import { downloadAsExcel } from '@/utils/excel'
import type { ExtractionLog } from '@/features/verification/types'

interface UseExtractionActionsOptions {
    modelId?: string
    onRetrySuccess?: (jobId: string, fileUrl: string) => void
}

export function useExtractionActions(options: UseExtractionActionsOptions = {}) {
    const { modelId, onRetrySuccess } = options
    const queryClient = useQueryClient()

    const invalidateLogs = async () => {
        if (modelId) {
            await queryClient.invalidateQueries({ queryKey: ['extraction-logs', modelId] })
        }
        await queryClient.invalidateQueries({ queryKey: ['extraction-logs-all'] })
    }

    const handleRetry = async (log: ExtractionLog) => {
        try {
            const res = await apiClient.post(`/extraction/retry/${log.id}`)
            toast.success('재시도 작업이 시작되었습니다.')
            await invalidateLogs()

            if (onRetrySuccess && res.data?.job_id) {
                onRetrySuccess(res.data.job_id, res.data.file_url)
            }
            return res.data
        } catch (e: any) {
            toast.error('재시도 요청 실패: ' + (e?.response?.data?.detail || '알 수 없는 오류'))
            throw e
        }
    }

    const handleDownload = async (log: ExtractionLog) => {
        if (!log.extracted_data) {
            toast.error('추출 데이터가 없습니다')
            return
        }
        
        try {
            await apiClient.post('/extraction/logs/audit/export', {
                log_ids: [log.id],
                model_id: log.model_id
            })
        } catch (e) {
            console.error('Failed to log export audit', e)
        }

        downloadAsExcel(
            [{ filename: log.filename, ...log.extracted_data }],
            `${log.filename}_${new Date(log.created_at).toLocaleDateString()}`
        )
        toast.success('Excel 다운로드 완료!')
    }

    const handleDelete = async (log: ExtractionLog) => {
        if (!confirm('정말로 이 기록을 삭제하시겠습니까? 복구할 수 없습니다.')) return false
        try {
            // Use logs bulk delete endpoint for correct log deletion
            await extractionApi.deleteLogs([log.id])
            toast.success('기록이 삭제되었습니다.')
            await invalidateLogs()
            return true
        } catch {
            toast.error('삭제 실패')
            return false
        }
    }

    const handleCancel = async (log: ExtractionLog) => {
        const cancelId = log.job_id || log.id;
        if (!cancelId) {
            toast.error('취소할 작업이 없습니다')
            return false
        }
        if (!confirm('정말로 이 작업을 취소하시겠습니까?')) return false
        try {
            await extractionApi.cancelJob(cancelId)
            toast.success('작업이 취소되었습니다.')
            await invalidateLogs()
            return true
        } catch {
            toast.error('작업 취소 실패')
            return false
        }
    }

    const handleUnmask = async (logId: string, path: string) => {
        try {
            const res = await apiClient.post(`/extraction/logs/${logId}/unmask`, { path })
            toast.success('원본 데이터를 성공적으로 불러왔습니다', { position: 'top-center' })
            return res.data.value
        } catch (e: any) {
            toast.error('마스킹 해제 실패: ' + (e?.response?.data?.detail || '알 수 없는 오류'), { position: 'top-center' })
            throw e
        }
    }

    return {
        handleRetry,
        handleDownload,
        handleDelete,
        handleCancel,
        handleUnmask
    }
}
