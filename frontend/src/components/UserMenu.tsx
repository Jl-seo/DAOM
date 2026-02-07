import { useState, useRef, useEffect } from 'react'
import { LogOut, User, ChevronDown, Settings, Sun, Moon, Globe } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth'
import { useSiteConfig } from './SiteConfigProvider'

// Locale configuration
const LOCALES = ['ko', 'en'] as const
type LocaleType = typeof LOCALES[number]
const LOCALE_NAMES: Record<LocaleType, string> = {
    ko: '한국어',
    en: 'English'
}

export function UserMenu() {
    const navigate = useNavigate()
    const { user, logout } = useAuth()
    const { updateConfig, resolvedTheme } = useSiteConfig()
    const { t, i18n } = useTranslation()
    const [isOpen, setIsOpen] = useState(false)
    const [showLangMenu, setShowLangMenu] = useState(false)
    const menuRef = useRef<HTMLDivElement>(null)

    // 외부 클릭 시 닫기
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setIsOpen(false)
                setShowLangMenu(false)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    if (!user) return null

    // 사용자 이름 추출
    const displayName = user.name || user.username || user.localAccountId?.slice(0, 8) || t('common.labels.user')
    const email = user.username || ''
    const initials = displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)

    const toggleTheme = () => {
        updateConfig({ theme: resolvedTheme === 'dark' ? 'light' : 'dark' })
    }

    const changeLanguage = (lang: LocaleType) => {
        i18n.changeLanguage(lang)
        setShowLangMenu(false)
    }

    const currentLang = (i18n.language || 'ko') as LocaleType

    return (
        <div className="relative" ref={menuRef}>
            {/* 사용자 버튼 */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-sidebar-accent transition-colors group"
            >
                {/* 아바타 */}
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center text-primary-foreground font-bold text-sm shadow-lg">
                    {initials}
                </div>

                {/* 이름 */}
                <div className="flex-1 text-left overflow-hidden">
                    <div className="text-sm font-semibold text-sidebar-foreground truncate">{displayName}</div>
                    <div className="text-xs text-sidebar-foreground/60 truncate">{email}</div>
                </div>

                {/* 화살표 */}
                <ChevronDown
                    className={`w-4 h-4 text-sidebar-foreground/60 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                />
            </button>

            {/* 드롭다운 메뉴 */}
            {isOpen && (
                <div className="absolute bottom-full left-0 right-0 mb-2 bg-sidebar rounded-xl shadow-xl border border-sidebar-border overflow-hidden z-50">
                    <div className="p-3 border-b border-sidebar-border">
                        <div className="text-xs text-sidebar-foreground/60 mb-1">{t('common.status.allowed')}</div>
                        <div className="text-sm font-medium text-sidebar-foreground truncate">{email}</div>
                    </div>

                    <div className="p-2">
                        <button
                            onClick={() => {
                                setIsOpen(false)
                                navigate('/profile')
                            }}
                            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                        >
                            <User className="w-4 h-4" />
                            <span className="text-sm">{t('common.labels.user')}</span>
                        </button>

                        <button
                            onClick={() => {
                                setIsOpen(false)
                                navigate('/admin/settings')
                            }}
                            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                        >
                            <Settings className="w-4 h-4" />
                            <span className="text-sm">{t('common.labels.settings')}</span>
                        </button>

                        {/* Theme Toggle */}
                        <button
                            onClick={toggleTheme}
                            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                        >
                            {resolvedTheme === 'dark' ? (
                                <Sun className="w-4 h-4" />
                            ) : (
                                <Moon className="w-4 h-4" />
                            )}
                            <span className="text-sm">
                                {resolvedTheme === 'dark' ? t('theme.modes.light') : t('theme.modes.dark')}
                            </span>
                        </button>

                        {/* Language Selector */}
                        <div className="relative">
                            <button
                                onClick={() => setShowLangMenu(!showLangMenu)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                            >
                                <Globe className="w-4 h-4" />
                                <span className="text-sm flex-1 text-left">{LOCALE_NAMES[currentLang]}</span>
                                <ChevronDown className={`w-3 h-3 transition-transform ${showLangMenu ? 'rotate-180' : ''}`} />
                            </button>

                            {showLangMenu && (
                                <div className="absolute left-0 right-0 top-full mt-1 bg-sidebar border border-sidebar-border rounded-lg shadow-lg overflow-hidden z-50">
                                    {LOCALES.map((lang) => (
                                        <button
                                            key={lang}
                                            onClick={() => changeLanguage(lang)}
                                            className={`w-full px-3 py-2 text-sm text-left hover:bg-sidebar-accent transition-colors ${currentLang === lang ? 'bg-primary/10 text-primary font-medium' : 'text-sidebar-foreground/80'
                                                }`}
                                        >
                                            {LOCALE_NAMES[lang]}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="my-1 border-t border-sidebar-border" />

                        <button
                            onClick={() => {
                                setIsOpen(false)
                                logout()
                            }}
                            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-destructive hover:bg-destructive/10 transition-colors"
                        >
                            <LogOut className="w-4 h-4" />
                            <span className="text-sm">{t('common.actions.close')}</span>
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
