import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import {
    LayoutDashboard,
    FileText,
    Settings,
    Users,
    History,
    Palette,
    Loader2,
    ClipboardList,
    PanelLeftClose,
    PanelLeftOpen
} from 'lucide-react'
import { clsx } from 'clsx'
import { modelsApi } from '../lib/api'
import { SidebarItem } from './SidebarItem'
import { useSiteConfig } from './SiteConfigProvider'
import { UserMenu } from './UserMenu'

interface Model {
    id: string
    name: string
    description: string
    is_active?: boolean
}

export function Sidebar({ className, onClose, collapsed = false, onToggleCollapse }: { className?: string, onClose?: () => void, collapsed?: boolean, onToggleCollapse?: () => void }) {
    const navigate = useNavigate()
    const location = useLocation()
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

    const handleNavigate = (path: string) => {
        navigate(path)
        if (onClose) onClose()
    }

    // Determine active menu from URL path
    const getActiveGroup = () => {
        if (location.pathname.startsWith('/models/')) return 'models'
        if (location.pathname === '/models') return 'models'
        if (location.pathname === '/admin/model-studio') return 'admin-model'
        if (location.pathname.startsWith('/admin/')) return 'admin'
        return null
    }

    const activeGroup = getActiveGroup()

    // Check if specific path is active
    const isPathActive = (path: string) => {
        if (path === '/models' && location.pathname === '/models') return true
        if (path !== '/models' && location.pathname === path) return true
        if (path.startsWith('/models/') && location.pathname.startsWith(path)) return true
        return false
    }

    return (
        <aside className={clsx("bg-sidebar text-sidebar-foreground flex flex-col h-full transition-all duration-200", className || (collapsed ? "w-16" : "w-64"))}>
            {/* Logo */}
            <div className={clsx("border-b border-sidebar-border", collapsed ? "p-3" : "p-6")}>
                <div className={clsx("flex items-center", collapsed ? "justify-center" : "justify-between")}>
                    <button
                        onClick={() => handleNavigate('/models')}
                        className={clsx("flex items-center text-left hover:opacity-80 transition-opacity min-w-0", collapsed ? "justify-center" : "gap-3 flex-1")}
                        title={collapsed ? config.siteName : undefined}
                    >
                        {config.logoUrl ? (
                            <img
                                src={config.logoUrl}
                                alt="Logo"
                                className={clsx("rounded-xl object-contain flex-shrink-0", collapsed ? "w-8 h-8" : "w-10 h-10")}
                            />
                        ) : (
                            <div className="bg-gradient-to-br from-primary to-chart-5 p-2 rounded-xl flex-shrink-0">
                                <LayoutDashboard className="w-6 h-6" />
                            </div>
                        )}
                        {!collapsed && (
                            <div className="min-w-0">
                                <h1 className="text-xl font-bold">{config.siteName}</h1>
                                <p className="text-xs text-sidebar-foreground/60 truncate">{config.siteDescription}</p>
                            </div>
                        )}
                    </button>
                    {onToggleCollapse && !collapsed && (
                        <button
                            onClick={onToggleCollapse}
                            className="flex-shrink-0 p-1.5 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-sidebar-accent/30 transition-colors ml-2"
                            title="사이드바 접기"
                        >
                            <PanelLeftClose className="w-4 h-4" />
                        </button>
                    )}
                </div>
                {onToggleCollapse && collapsed && (
                    <button
                        onClick={onToggleCollapse}
                        className="w-full flex items-center justify-center p-1.5 mt-2 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-sidebar-accent/30 transition-colors"
                        title="사이드바 펼치기"
                    >
                        <PanelLeftOpen className="w-4 h-4" />
                    </button>
                )}

                <button
                    onClick={() => handleNavigate('/quick-extraction')}
                    className={clsx(
                        "mt-4 w-full flex items-center justify-center font-semibold rounded-lg shadow-md transition-all active:scale-[0.98]",
                        collapsed ? "p-2" : "gap-2 py-2.5",
                        location.pathname === '/quick-extraction'
                            ? "bg-sidebar-primary text-sidebar-primary-foreground"
                            : "bg-gradient-to-r from-primary to-chart-5 text-primary-foreground hover:opacity-90"
                    )}
                    title={collapsed ? '빠른 추출 시작' : undefined}
                >
                    <span className="text-lg">⚡</span> {!collapsed && '빠른 추출 시작'}
                </button>
            </div>

            {/* Navigation */}
            <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
                {/* Models Group */}
                <div>
                    <SidebarItem
                        icon={FileText}
                        label={collapsed ? '' : '문서 추출'}
                        isActive={activeGroup === 'models'}
                        hasSubmenu={!collapsed}
                        isExpanded={!collapsed && expandedGroups.includes('models')}
                        onClick={() => collapsed ? handleNavigate('/models') : toggleGroup('models')}
                        tooltip={collapsed ? '문서 추출' : undefined}
                    />

                    {/* Submenu - hidden when collapsed */}
                    {!collapsed && expandedGroups.includes('models') && (
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
                                models
                                    .filter(model => model.is_active !== false)
                                    .map(model => (
                                        <button
                                            key={model.id}
                                            onClick={() => handleNavigate(`/models/${model.id}`)}
                                            className={clsx(
                                                "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                                isPathActive(`/models/${model.id}`)
                                                    ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                                    : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                            )}
                                        >
                                            <span className="text-lg">📄</span>
                                            <span className="flex-1 text-left truncate">{model.name}</span>
                                            {isPathActive(`/models/${model.id}`) && (
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
                        label={collapsed ? '' : '모델 관리'}
                        isActive={activeGroup === 'admin-model'}
                        hasSubmenu={!collapsed}
                        isExpanded={!collapsed && expandedGroups.includes('admin-model')}
                        onClick={() => collapsed ? handleNavigate('/admin/model-studio') : toggleGroup('admin-model')}
                        tooltip={collapsed ? '모델 관리' : undefined}
                    />

                    {!collapsed && expandedGroups.includes('admin-model') && (
                        <div className="mt-1 ml-4 space-y-1">
                            <button
                                onClick={() => handleNavigate('/admin/model-studio')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/admin/model-studio')
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <ClipboardList className="w-4 h-4" />
                                <span className="flex-1 text-left">모델 스튜디오</span>
                            </button>
                            <button
                                onClick={() => handleNavigate('/models')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/models')
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
                        label={collapsed ? '' : '시스템 설정'}
                        isActive={activeGroup === 'admin'}
                        hasSubmenu={!collapsed}
                        isExpanded={!collapsed && expandedGroups.includes('admin')}
                        onClick={() => collapsed ? handleNavigate('/admin/dashboard') : toggleGroup('admin')}
                        tooltip={collapsed ? '시스템 설정' : undefined}
                    />

                    {!collapsed && expandedGroups.includes('admin') && (
                        <div className="mt-1 ml-4 space-y-1">
                            <button
                                onClick={() => handleNavigate('/admin/dashboard')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/admin/dashboard')
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <LayoutDashboard className="w-4 h-4" />
                                <span className="flex-1 text-left">대시보드</span>
                            </button>
                            <button
                                onClick={() => handleNavigate('/admin/audit')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/admin/audit')
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <ClipboardList className="w-4 h-4" />
                                <span className="flex-1 text-left">활동 로그</span>
                            </button>
                            <button
                                onClick={() => handleNavigate('/admin/settings')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/admin/settings')
                                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <Settings className="w-4 h-4" />
                                <span className="flex-1 text-left">일반 설정</span>
                            </button>
                            <button
                                onClick={() => handleNavigate('/admin/users')}
                                className={clsx(
                                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                                    isPathActive('/admin/users')
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
                    label={collapsed ? '' : '전체 추출 기록'}
                    isActive={location.pathname === '/history'}
                    onClick={() => handleNavigate('/history')}
                    tooltip={collapsed ? '전체 추출 기록' : undefined}
                />

            </nav>

            {/* User Menu */}
            {!collapsed && (
                <div className="border-t border-sidebar-border">
                    <div className="p-4">
                        <UserMenu />
                    </div>
                </div>
            )}
        </aside >
    )
}
