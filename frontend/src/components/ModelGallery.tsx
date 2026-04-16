/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileText, ArrowRight, CircleNotch, SquaresFour, PlusCircle, Sparkle, MagnifyingGlass, GitDiff, Stack, Copy } from '@phosphor-icons/react'
import axios from 'axios'
import { API_CONFIG } from '../constants'
import { modelsApi } from '../lib/api'
import { toast } from 'sonner'
import { useSiteConfig } from './SiteConfigProvider'
import { useAuth } from '../auth/AuthContext'
import clsx from 'clsx'

const API_BASE = API_CONFIG.BASE_URL

interface Model {
    id: string
    name: string
    description: string
    fields: Array<{ key: string; label: string; type: string }>
    data_structure?: string
    model_type?: 'extraction' | 'comparison'
}

type TabType = 'all' | 'extraction' | 'comparison'

export function ModelGallery() {
    const navigate = useNavigate()
    const { t } = useTranslation()
    const [models, setModels] = useState<Model[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
    const [activeTab, setActiveTab] = useState<TabType>('all')
    const { config } = useSiteConfig()
    const { isSuperAdmin, getAccessToken } = useAuth()

    useEffect(() => {
        loadModels()
    }, [])

    const loadModels = async () => {
        try {
            const token = await getAccessToken()
            const res = await axios.get(`${API_BASE}/models`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            })
            setModels(res.data)
        } catch {
            toast.error(t('gallery.errors.load_failed'))
        } finally {
            setLoading(false)
        }
    }

    // Count models by type
    const counts = useMemo(() => ({
        all: models.length,
        extraction: models.filter(m => m.model_type !== 'comparison').length,
        comparison: models.filter(m => m.model_type === 'comparison').length
    }), [models])

    // Filter by tab and search
    const filteredModels = useMemo(() => {
        let result = models

        if (activeTab === 'extraction') {
            result = result.filter(m => m.model_type !== 'comparison')
        } else if (activeTab === 'comparison') {
            result = result.filter(m => m.model_type === 'comparison')
        }

        if (searchQuery) {
            const query = searchQuery.toLowerCase()
            result = result.filter(m =>
                m.name.toLowerCase().includes(query) ||
                m.description?.toLowerCase().includes(query)
            )
        }

        return result
    }, [models, activeTab, searchQuery])

    const handleCopy = async (modelId: string, e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        try {
            await modelsApi.copy(modelId)
            toast.success(t('gallery.success.copied'))
            await loadModels()
        } catch (error) {
            toast.error(t('gallery.errors.copy_failed'))
        }
    }

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <CircleNotch size={32} className="animate-spin text-primary" />
            </div>
        )
    }

    const tabs: { key: TabType; icon: React.ReactNode; color: string }[] = [
        { key: 'all', icon: <Stack size={16} weight="duotone" />, color: 'text-foreground' },
        { key: 'extraction', icon: <FileText size={16} weight="duotone" />, color: 'text-primary' },
        { key: 'comparison', icon: <GitDiff size={16} weight="duotone" />, color: 'text-chart-5' },
    ]

    const getEmptyMessage = () => {
        if (searchQuery) return t('gallery.empty.no_results')
        if (activeTab === 'comparison') return t('gallery.empty.no_models_filtered', { type: t('gallery.tabs.comparison') })
        if (activeTab === 'extraction') return t('gallery.empty.no_models_filtered', { type: t('gallery.tabs.extraction') })
        return t('gallery.empty.no_models')
    }

    return (
        <div className="flex-1 overflow-auto">
            {/* Compact Hero Section */}
            <div className="relative overflow-hidden border-b border-border">
                <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-chart-5/5 to-chart-2/5" />

                <div className="relative max-w-6xl mx-auto px-4 md:px-8 py-8">
                    <div className="flex flex-col md:flex-row items-center gap-6">
                        <div className="w-16 h-16 bg-gradient-to-br from-primary via-chart-5 to-chart-2 rounded-2xl flex items-center justify-center shadow-xl">
                            <Sparkle size={32} weight="fill" className="text-white" />
                        </div>

                        <div className="text-center md:text-left flex-1">
                            <h1 className="text-2xl md:text-3xl font-black text-foreground mb-1">
                                {config.siteName}
                            </h1>
                            <p className="text-muted-foreground text-sm">
                                {t('gallery.hero.subtitle')}
                            </p>
                        </div>

                        {isSuperAdmin && (
                            <button
                                onClick={() => navigate('/admin/model-studio')}
                                className="inline-flex items-center px-5 py-2.5 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20"
                            >
                                <PlusCircle size={16} weight="bold" className="mr-2" />
                                {t('gallery.actions.new_model')}
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="max-w-6xl mx-auto px-4 md:px-8 py-6">
                {/* Tab Navigation + Search */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                    {/* Tabs */}
                    <div className="flex gap-1 p-1 bg-muted/50 rounded-xl w-fit">
                        {tabs.map(tab => (
                            <button
                                key={tab.key}
                                onClick={() => setActiveTab(tab.key)}
                                className={clsx(
                                    "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                                    activeTab === tab.key
                                        ? "bg-background shadow-sm text-foreground"
                                        : "text-muted-foreground hover:text-foreground hover:bg-background/50"
                                )}
                            >
                                <span className={activeTab === tab.key ? tab.color : undefined}>
                                    {tab.icon}
                                </span>
                                {t(`gallery.tabs.${tab.key}`)}
                                <span className={clsx(
                                    "ml-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold",
                                    activeTab === tab.key
                                        ? "bg-muted text-muted-foreground"
                                        : "bg-muted/50 text-muted-foreground/70"
                                )}>
                                    {counts[tab.key]}
                                </span>
                            </button>
                        ))}
                    </div>

                    {/* Search */}
                    <div className="relative max-w-xs w-full">
                        <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder={t('gallery.search.placeholder')}
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                        />
                    </div>
                </div>

                {/* Model Grid */}
                {filteredModels.length === 0 ? (
                    <div className="text-center py-16 bg-muted/30 rounded-2xl border-2 border-dashed border-border">
                        <div className="w-16 h-16 mx-auto mb-4 bg-background rounded-2xl flex items-center justify-center">
                            <SquaresFour size={32} weight="duotone" className="text-muted-foreground" />
                        </div>
                        <h3 className="text-lg font-semibold text-foreground mb-1">
                            {getEmptyMessage()}
                        </h3>
                        <p className="text-muted-foreground text-sm mb-6">
                            {searchQuery ? t('gallery.empty.try_different') : t('gallery.empty.create_first')}
                        </p>
                        {!searchQuery && isSuperAdmin && (
                            <button
                                onClick={() => navigate('/admin/model-studio')}
                                className="inline-flex items-center px-4 py-2 rounded-lg bg-primary text-white font-medium hover:bg-primary/90"
                            >
                                <PlusCircle size={16} weight="bold" className="mr-2" />
                                {t('gallery.actions.create_model')}
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {filteredModels.map((model) => {
                            const isComparison = model.model_type === 'comparison'
                            return (
                                <button
                                    key={model.id}
                                    onClick={() => navigate(`/models/${model.id}`)}
                                    className={clsx(
                                        "group relative flex flex-col p-4 rounded-xl border-2 transition-all duration-200 text-left",
                                        "hover:shadow-lg hover:-translate-y-0.5",
                                        isComparison
                                            ? "bg-gradient-to-br from-chart-5/5 to-transparent border-chart-5/20 hover:border-chart-5/50"
                                            : "bg-card border-border hover:border-primary/50"
                                    )}
                                >
                                    {/* Type Badge */}
                                    <div className="flex items-center justify-between mb-3">
                                        <div className={clsx(
                                            "w-10 h-10 rounded-xl flex items-center justify-center",
                                            isComparison
                                                ? "bg-chart-5/10 group-hover:bg-chart-5/20"
                                                : "bg-primary/10 group-hover:bg-primary/20"
                                        )}>
                                            {isComparison
                                                ? <GitDiff size={20} weight="duotone" className="text-chart-5" />
                                                : <FileText size={20} weight="duotone" className="text-primary" />
                                            }
                                        </div>
                                        <span className={clsx(
                                            "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider",
                                            isComparison
                                                ? "bg-chart-5/10 text-chart-5 border border-chart-5/20"
                                                : "bg-primary/10 text-primary border border-primary/20"
                                        )}>
                                            {t(`gallery.tabs.${isComparison ? 'comparison' : 'extraction'}`)}
                                        </span>
                                    </div>

                                    {/* Title & Description */}
                                    <h3 className={clsx(
                                        "font-bold mb-1 line-clamp-1 transition-colors",
                                        isComparison ? "group-hover:text-chart-5" : "group-hover:text-primary"
                                    )}>
                                        {model.name}
                                    </h3>
                                    <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[2rem]">
                                        {model.description || t('gallery.card.no_description')}
                                    </p>

                                    {/* Footer */}
                                    <div className="flex items-center justify-between mt-auto pt-3 border-t border-border/50">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-muted-foreground bg-muted/50 px-2 py-1 rounded-md">
                                                {t('gallery.card.field_count', { count: model.fields?.length || 0 })}
                                            </span>
                                            <div 
                                                role="button"
                                                onClick={(e) => handleCopy(model.id, e)}
                                                className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors opacity-0 group-hover:opacity-100"
                                                title={t('gallery.actions.copy') || 'Copy'}
                                            >
                                                <Copy size={14} weight="bold" />
                                            </div>
                                        </div>
                                        <span className={clsx(
                                            "text-xs font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity",
                                            isComparison ? "text-chart-5" : "text-primary"
                                        )}>
                                            {t('gallery.actions.start')}
                                            <ArrowRight size={12} />
                                        </span>
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                )}
            </div>
        </div>
    )
}
