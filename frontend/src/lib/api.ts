/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Centralized API Client for DAOM
 * 
 * Consolidates all API calls with consistent error handling,
 * authentication headers, and type safety.
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { API_CONFIG } from '../constants'
import { msalInstance } from '../main'
import { loginRequest } from '../auth/authConfig'

// Create axios instance with base configuration
const apiClient: AxiosInstance = axios.create({
    baseURL: API_CONFIG.BASE_URL,
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json',
    },
})

// Request interceptor for auth token
apiClient.interceptors.request.use(
    async (config) => {
        try {
            const accounts = msalInstance.getAllAccounts()
            if (accounts.length > 0) {
                const response = await msalInstance.acquireTokenSilent({
                    ...loginRequest,
                    account: accounts[0]
                })
                if (response.accessToken) {
                    config.headers.Authorization = `Bearer ${response.accessToken}`
                }
            }
        } catch (error) {
            console.error('Failed to get access token:', error)
        }
        return config
    },
    (error) => Promise.reject(error)
)

// Response interceptor for error handling
apiClient.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
        if (error.response?.status === 401) {
            // Handle unauthorized - redirect to login
            console.error('Unauthorized - redirecting to login')
        }
        return Promise.reject(error)
    }
)

// ============================================
// Models API
// ============================================

import type { Model, Field as ModelField } from '../types/model'

export type { Model, ModelField }

export const modelsApi = {
    getAll: () =>
        apiClient.get<Model[]>('/models'),

    getById: (id: string) =>
        apiClient.get<Model>(`/models/${id}`),

    create: (model: Omit<Model, 'id'>) =>
        apiClient.post<Model>('/models', model),

    update: (id: string, model: Partial<Model>) =>
        apiClient.put<Model>(`/models/${id}`, model),

    delete: (id: string) =>
        apiClient.delete(`/models/${id}`),

    getOptions: () =>
        apiClient.get<{ id: string; name: string }[]>('/models/options/list'),

    analyzeSample: (formData: FormData) =>
        apiClient.post<{ fields: any[]; raw_result: any }>('/models/analyze-sample', formData),

    refineSchema: (fields: any[], instruction: string) =>
        apiClient.post('/models/schema/refine', { fields, instruction }),
}

// ============================================
// Documents API
// ============================================

export interface ExtractionResult {
    extracted_data: Record<string, unknown>
    confidence?: number
    processing_time?: number
}

export const documentsApi = {
    extract: (modelId: string, file: File) => {
        const formData = new FormData()
        formData.append('file', file)
        return apiClient.post<ExtractionResult>(`/documents/extract/${modelId}`, formData)
    },

    batchExtract: (modelId: string, files: File[]) => {
        const formData = new FormData()
        files.forEach((file) => formData.append('files', file))
        return apiClient.post<ExtractionResult[]>(`/documents/batch/${modelId}`, formData)
    },
}

export const extractionApi = {
    getJob: (jobId: string) =>
        apiClient.get<import('../types/extraction').ExtractionJob>(`/extraction/job/${jobId}`),

    uploadFile: (modelId: string, file: File) => {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('model_id', modelId)
        // extraction_preview.py start-job expects 'file' (singular UploadFile)
        return apiClient.post<{ job_id: string; file_url: string; log_id?: string }>(`/extraction/start-job`, formData)
    },

    deleteJob: (jobId: string) =>
        apiClient.delete(`/extraction/job/${jobId}`),

    deleteLogs: (logIds: string[]) =>
        apiClient.delete(`/extraction/logs/bulk`, { data: logIds }),

    cancelJob: (jobId: string) =>
        apiClient.post(`/extraction/job/${jobId}/cancel`)
}

// ============================================
// Templates API
// ============================================

export interface TemplateChatRequest {
    message: string
    current_config: Record<string, unknown>
    model_fields: ModelField[]
}

export const templatesApi = {
    chat: (request: TemplateChatRequest) =>
        apiClient.post('/templates/chat', request),
}

// ============================================
// Audit API
// ============================================

export interface AuditLog {
    id: string
    timestamp: string
    user_id: string
    user_email: string
    action: string
    resource_type: string
    resource_id: string
    details?: Record<string, unknown>
    ip_address?: string
}

export interface AuditLogsResponse {
    items: AuditLog[]
    total: number
}

export const auditApi = {
    getLogs: (params?: {
        action?: string
        resource_type?: string
        start_date?: string
        end_date?: string
        limit?: number
        offset?: number
    }) => apiClient.get<AuditLogsResponse>('/audit', { params }),
}

// ============================================
// Settings API
// ============================================

export interface AppSettings {
    llm_endpoint?: string
    llm_api_key?: string
    cosmos_endpoint?: string
    cosmos_key?: string
    [key: string]: unknown
}

export const settingsApi = {
    get: () =>
        apiClient.get<AppSettings>('/settings'),

    update: (settings: Partial<AppSettings>) =>
        apiClient.put('/settings', settings),

    test: (type: 'llm' | 'cosmos') =>
        apiClient.post(`/settings/test/${type}`),
}

// ============================================
// Users API
// ============================================

export interface UserInfo {
    id: string
    email: string
    name: string
    role: 'Admin' | 'Editor' | 'Viewer'
    tenant_id: string
    created_at: string
    last_login: string
    groups: string[]
}

export const usersApi = {
    getMe: () =>
        apiClient.get<UserInfo>('/users/me'),

    getAll: (search?: string) =>
        apiClient.get<UserInfo[]>('/users', { params: { search } }),

    getById: (userId: string) =>
        apiClient.get<UserInfo>(`/users/${userId}`),

    updateRole: (userId: string, role: string) =>
        apiClient.put(`/users/${userId}/role`, { role }),
}

// ============================================
// Groups API
// ============================================

export interface GroupMember {
    type: 'user' | 'entra_group'
    id: string
    displayName: string
}

export interface ModelPermission {
    modelId: string
    modelName: string
    role: 'Admin' | 'User'
}

export interface GroupPermissions {
    superAdmin: boolean
    models: ModelPermission[]
    menus: string[]  // Menu IDs
}

export interface GroupInfo {
    id: string
    name: string
    description: string
    tenant_id: string
    members: GroupMember[]
    permissions: GroupPermissions
    created_by: string
    created_at: string
}

export const groupsApi = {
    getAll: () =>
        apiClient.get<GroupInfo[]>('/groups'),

    create: (name: string, description: string, superAdmin: boolean = false) =>
        apiClient.post<GroupInfo>('/groups', { name, description, superAdmin }),

    update: (groupId: string, name?: string, description?: string) =>
        apiClient.put<GroupInfo>(`/groups/${groupId}`, { name, description }),

    getById: (groupId: string) =>
        apiClient.get<GroupInfo>(`/groups/${groupId}`),

    addMember: (groupId: string, type: 'user' | 'entra_group', id: string, displayName: string) =>
        apiClient.post(`/groups/${groupId}/members`, { type, id, displayName }),

    removeMember: (groupId: string, memberId: string) =>
        apiClient.delete(`/groups/${groupId}/members/${memberId}`),

    setPermissions: (groupId: string, superAdmin: boolean, models: ModelPermission[], menus: string[]) =>
        apiClient.put(`/groups/${groupId}/permissions`, { superAdmin, models, menus }),

    deleteGroup: (groupId: string) =>
        apiClient.delete(`/groups/${groupId}`),
}

// ============================================
// Menus API
// ============================================

export interface MenuInfo {
    id: string
    name: string
    icon: string
    order: number
    parent: string | null
}

export const menusApi = {
    getAll: () =>
        apiClient.get<MenuInfo[]>('/menus'),

    getAccessible: () =>
        apiClient.get<MenuInfo[]>('/menus/accessible'),

    update: (menuId: string, name?: string, icon?: string, order?: number) =>
        apiClient.put(`/menus/${menuId}`, { name, icon, order }),
}

// Export the raw client for edge cases
export { apiClient }
export default apiClient

