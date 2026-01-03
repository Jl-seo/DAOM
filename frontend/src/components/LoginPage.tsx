import { useAuth } from '../auth'
import { useSiteConfig } from './SiteConfigProvider'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export function LoginPage() {
    const { login, isLoading } = useAuth()
    const { config } = useSiteConfig()

    return (
        <div className="min-h-screen bg-gradient-to-br from-sidebar via-primary/20 to-sidebar flex items-center justify-center p-6">
            <div className="max-w-md w-full">
                {/* Logo & Title */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-card/10 backdrop-blur-lg rounded-2xl mb-6">
                        <span className="text-4xl">📄</span>
                    </div>
                    <h1 className="text-4xl font-black text-primary-foreground mb-2">{config.siteName}</h1>
                    <p className="text-primary/80 text-lg">Document AI Output Manager</p>
                    <p className="text-muted-foreground text-sm mt-2">{config.siteDescription}</p>
                </div>

                {/* Login Card */}
                <Card className="bg-card/10 backdrop-blur-lg p-8 shadow-2xl border-0">
                    <div className="text-center mb-6">
                        <h2 className="text-xl font-bold text-primary-foreground mb-2">로그인</h2>
                        <p className="text-muted-foreground text-sm">Microsoft 계정으로 시작하세요</p>
                    </div>

                    <Button
                        onClick={login}
                        disabled={isLoading}
                        variant="secondary"
                        className="w-full py-6 text-base font-bold gap-3"
                    >
                        {isLoading ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <>
                                <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none">
                                    <rect width="10" height="10" fill="#F25022" />
                                    <rect x="11" width="10" height="10" fill="#7FBA00" />
                                    <rect y="11" width="10" height="10" fill="#00A4EF" />
                                    <rect x="11" y="11" width="10" height="10" fill="#FFB900" />
                                </svg>
                                Microsoft로 로그인
                            </>
                        )}
                    </Button>

                    <p className="text-center text-muted-foreground text-xs mt-6">
                        조직 계정 또는 개인 Microsoft 계정으로 로그인할 수 있습니다
                    </p>
                </Card>

                {/* Footer */}
                <p className="text-center text-muted-foreground/60 text-xs mt-8">
                    © 2026 {config.siteName}. Powered by Azure AI.
                </p>
            </div>
        </div>
    )
}
