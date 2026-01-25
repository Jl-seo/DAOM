import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
    LayoutDashboard,
    FileText,
    Settings,
    Users,
    History,
    Palette,
    Loader2,
    ClipboardList
} from 'lucide-react'
import { clsx } from 'clsx'
import { modelsApi } from '../lib/api'
import { SidebarItem } from './SidebarItem'
import { useSiteConfig } from './SiteConfigProvider'
import { UserMenu } from './UserMenu'

export type MenuId = 'home' | 'profile' | `model-${string}` | 'model-studio' | 'model-gallery' | 'extraction-history' | 'admin-dashboard' | 'admin-audit' | 'settings-general' | 'settings-users' | 'quick-extraction'

interface SidebarProps {
    activeMenu: MenuId
    onMenuChange: (menu: MenuId) => void
    onQuickExtraction?: () => void
}

interface Model {
    id: string
    name: string
    description: string
}

export function Sidebar({ activeMenu, onMenuChange, onQuickExtraction, className, onClose }: SidebarProps & { className?: string, onClose?: () => void }) {
    const { config } = useSiteConfig()
    const [expandedGroups, setExpandedGroups] = useState<string[]>(['models'])

    // Load models with React Query for auto-refresh
    const { data: models = [], isLoading: loading } = useQuery({
        queryKey: ['models'],
        queryFn: async () => {
            const res = await modelsApi.getAll()
            return res.data as Model[]
        },
        refetchInterval: 5000  // Auto-refresh every 5 seconds
    })

    const toggleGroup = (groupId: string) => {
        setExpandedGroups(prev =>
            prev.includes(groupId)
                ? prev.filter(id => id !== groupId)
                : [...prev, groupId]
        )
    }

    const handleMenuChange = (menu: MenuId) => {
        onMenuChange(menu)
        if (onClose) onClose()
    }

    const getActiveGroup = () => {
        if (activeMenu.startsWith('model-')) return 'models'
        if (activeMenu === 'model-studio') return 'admin-model'
        if (activeMenu.startsWith('admin-') || activeMenu === 'settings-users' || activeMenu === 'settings-general') return 'admin'
        if (activeMenu.startsWith('settings-')) return 'settings'
        return null
    }

    const activeGroup = getActiveGroup()

    return (
        <aside className={clsx("bg-sidebar text-sidebar-foreground flex flex-col h-full", className || "w-64")}>
            {/* Logo */}
            <div className="p-6 border-b border-sidebar-border">
                <div className="flex items-center gap-3">
                    {config.logoUrl ? (
                        <img
                            src={config.logoUrl}
                            alt="Logo"
                            className="w-10 h-10 rounded-xl object-contain"
                        />
                    ) : (
                        <div className="bg-gradient-to-br from-primary to-chart-5 p-2 rounded-xl">
                            <LayoutDashboard className="w-6 h-6" />
                        </div>
                    )}
                    <div>
                        <h1 className="text-xl font-bold">{config.siteName}</h1>
                        <p className="text-xs text-sidebar-foreground/60">{config.siteDescription}</p>
                    </div>
                </div>

                <button
                    onClick={() => {
                        if (onQuickExtraction) onQuickExtraction()
                        handleMenuChange('quick-extraction')
                    }}
                    className={clsx(
                        "mt-6 w-full flex items-center justify-center gap-2 font-semibold py-2.5 rounded-lg shadow-md transition-all active:scale-[0.98]",
                        activeMenu === 'quick-extraction'
                            ? "bg-sidebar-primary text-sidebar-primary-foreground"
                            : "bg-gradient-to-r from-primary to-chart-5 text-primary-foreground hover:opacity-90"
                    )}
                >
                    <span className="text-lg">⚡</span> 빠른 추출 시작
                </button>
            </div>

            {/* Navigation */}
            <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
                {/* Models Group */}
                <div>
                    <SidebarItem
                        icon={FileText}
                        label="문서 추출"
                        isActive={activeGroup === 'models'}
                        hasSubmenu
                        isExpanded={expandedGroups.includes('models')}
                        onClick={() => toggleGroup('models')}
                    />

                    {/* Submenu */}
                    {expandedGroups.includes('models') && (
                        <div className="mt-1 ml-4 space-y-1">
                            {loading ? (
                                <div className="flex items-center gap-2 px-3 py-2 text-muted-foreground text-sm">
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    <span>모델 불러오는 중...</span>
                                </div>
                            ) : models.length === 0 ? (
                                <div className="px-3 py-2 text-muted-foreground text-sm">
                                    등록된 모델이 없습니다
                                </div>
                            ) : (
                                models.map(model => (
                                    <button
                                        key={model.id}
                                        onClick={() => handleMenuChange(`model-${model.id}` as MenuId)}
                                        className={clsx(
                                            "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                            activeMenu === `model-${model.id}`
                                                ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                                : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                        )}
                                    >
                                        <span className="text-lg">📄</span>
                                        <span className="flex-1 text-left truncate">{model.name}</span>
                                        {activeMenu === `model-${model.id}` && (
                                            <div className="w-1.5 h-1.5 rounded-full bg-sidebar-primary-foreground" />
                                        )}
                                    </button>
                                ))
                            )}
                        </div>
                    )}
                </div>

                {/* Admin Model Studio */}
                <div>
                    <SidebarItem
                        icon={Palette}
                        label="모델"
                        isActive={activeGroup === 'admin-model'}
                        hasSubmenu
                        isExpanded={expandedGroups.includes('admin-model')}
                        onClick={() => toggleGroup('admin-model')}
                    />

                    {expandedGroups.includes('admin-model') && (
                        <div className="mt-1 ml-4 space-y-1">
                            <button
                                onClick={() => handleMenuChange('model-studio')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'model-studio'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <ClipboardList className="w-4 h-4" />
                                <span className="flex-1 text-left">모델 스튜디오</span>
                            </button>
                            <button
                                onClick={() => handleMenuChange('model-gallery')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'model-gallery'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <LayoutDashboard className="w-4 h-4" />
                                <span className="flex-1 text-left">모델 갤러리</span>
                            </button>
                        </div>
                    )}
                </div>

                {/* Admin Group */}
                <div>
                    <SidebarItem
                        icon={Users}
                        label="관리자"
                        isActive={activeGroup === 'admin'}
                        hasSubmenu
                        isExpanded={expandedGroups.includes('admin')}
                        onClick={() => toggleGroup('admin')}
                    />

                    {expandedGroups.includes('admin') && (
                        <div className="mt-1 ml-4 space-y-1">
                            <button
                                onClick={() => handleMenuChange('admin-dashboard')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'admin-dashboard'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <LayoutDashboard className="w-4 h-4" />
                                <span className="flex-1 text-left">대시보드</span>
                            </button>
                            <button
                                onClick={() => handleMenuChange('admin-audit')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'admin-audit'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <ClipboardList className="w-4 h-4" />
                                <span className="flex-1 text-left">활동 로그</span>
                            </button>
                            <button
                                onClick={() => handleMenuChange('settings-general')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'settings-general'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <Settings className="w-4 h-4" />
                                <span className="flex-1 text-left">일반 설정</span>
                            </button>
                            <button
                                onClick={() => handleMenuChange('settings-users')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    activeMenu === 'settings-users'
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <Users className="w-4 h-4" />
                                <span className="flex-1 text-left">사용자 관리</span>
                            </button>
                        </div>
                    )}
                </div>

                {/* History */}
                <SidebarItem
                    icon={History}
                    label="전체 추출 기록"
                    isActive={activeMenu === 'extraction-history'}
                    onClick={() => handleMenuChange('extraction-history')}
                />

            </nav>

            {/* User Menu */}
            <div className="p-4 border-t border-sidebar-border">
                <UserMenu onMenuChange={handleMenuChange} />
            </div>
        </aside >
    )
}
