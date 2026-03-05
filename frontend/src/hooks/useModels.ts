/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback } from 'react'
import { modelsApi } from '../lib/api'
import { MESSAGES } from '../constants'
import type { Model } from '../types/model'

export function useModels() {
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const fetchModels = useCallback(async () => {
        try {
            const res = await modelsApi.getAll()
            setModels(res.data)
            setError(null)
        } catch (err) {
            console.error(err)
            setError('모델을 불러오는데 실패했습니다.')
        }
    }, [])

    const saveModel = useCallback(async (model: Partial<Model>) => {
        // 중복 저장 방지: 이미 저장 중이면 무시
        if (loading) {
            console.log('[useModels] Save already in progress, ignoring duplicate call')
            return { success: false, message: '저장 중입니다...', data: null }
        }

        setLoading(true)
        try {
            let savedModel: Model
            if (model.id) {
                const res = await modelsApi.update(model.id, model)
                savedModel = res.data
            } else {
                const res = await modelsApi.create(model as Omit<Model, 'id'>)
                savedModel = res.data
            }
            await fetchModels()
            return { success: true, message: MESSAGES.SAVE_SUCCESS, data: savedModel }
        } catch (err) {
            console.error(err)
            setError(MESSAGES.SAVE_ERROR)
            return { success: false, error: err, message: MESSAGES.SAVE_ERROR, data: null }
        } finally {
            setLoading(false)
        }
    }, [fetchModels, loading])

    const deleteModel = useCallback(async (id: string) => {
        // 중복 삭제 방지
        if (loading) {
            console.log('[useModels] Delete already in progress, ignoring')
            return { success: false, error: '처리 중입니다...' }
        }

        setLoading(true)
        try {
            await modelsApi.delete(id)
            await fetchModels()
            return { success: true }
        } catch (err) {
            console.error(err)
            setError('삭제에 실패했습니다.')
            return { success: false, error: err }
        } finally {
            setLoading(false)
        }
    }, [fetchModels, loading])

    // Restore useEffect for initial load
    useEffect(() => {
        fetchModels()
    }, [fetchModels])

    const fetchOptions = useCallback(async () => {
        try {
            const res = await modelsApi.getOptions()
            return res.data
        } catch (err) {
            console.error(err)
            return []
        }
    }, [])

    const fetchLlmOptions = useCallback(async () => {
        try {
            const res = await modelsApi.getLlmOptions()
            return res.data
        } catch (err) {
            console.error(err)
            return []
        }
    }, [])

    const analyzeSample = async (file: File, modelType: string) => {
        // 중복 분석 방지
        if (loading) {
            console.log('[useModels] Analysis already in progress, ignoring')
            return null
        }

        setLoading(true)
        setError(null)
        try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('model_type', modelType)
            const response = await modelsApi.analyzeSample(formData)
            return response.data
        } catch (err: any) {
            setError(err.message)
            throw err
        } finally {
            setLoading(false)
        }
    }

    const refineSchema = async (fields: any[], instruction: string) => {
        // 중복 스키마 정제 방지
        if (loading) {
            console.log('[useModels] Refinement already in progress, ignoring')
            return null
        }

        setLoading(true)
        try {
            const response = await modelsApi.refineSchema(fields, instruction)
            return response.data
        } catch (err: any) {
            setError('Refinement failed')
            throw err
        } finally {
            setLoading(false)
        }
    }

    return {
        models,
        loading,
        error,
        fetchModels,
        saveModel,
        deleteModel,
        fetchOptions,
        fetchLlmOptions,
        analyzeSample,
        refineSchema
    }
}
