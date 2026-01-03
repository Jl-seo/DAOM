import { useState } from 'react'
import { User, Mail, Building, Shield, Calendar } from 'lucide-react'
import { useAuth } from '../auth'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function ProfilePage() {
    const { user } = useAuth()
    const [activeTab, setActiveTab] = useState<'profile' | 'security'>('profile')

    if (!user) return null

    const displayName = user.name || user.username || '사용자'
    const email = user.username || ''
    const tenantId = user.tenantId || ''
    const initials = displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)

    return (
        <div className="max-w-4xl mx-auto">
            {/* Profile Header */}
            <div className="bg-gradient-to-r from-primary to-chart-5 rounded-2xl p-8 mb-6">
                <div className="flex items-center gap-6">
                    <div className="w-24 h-24 rounded-full bg-primary-foreground/20 backdrop-blur flex items-center justify-center text-primary-foreground font-bold text-3xl shadow-xl">
                        {initials}
                    </div>
                    <div className="text-primary-foreground">
                        <h1 className="text-3xl font-bold">{displayName}</h1>
                        <p className="text-primary-foreground/80 flex items-center gap-2 mt-1">
                            <Mail className="w-4 h-4" />
                            {email}
                        </p>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-6">
                <Button
                    variant={activeTab === 'profile' ? 'default' : 'outline'}
                    onClick={() => setActiveTab('profile')}
                >
                    프로필 정보
                </Button>
                <Button
                    variant={activeTab === 'security' ? 'default' : 'outline'}
                    onClick={() => setActiveTab('security')}
                >
                    보안
                </Button>
            </div>

            {/* Content */}
            <Card className="overflow-hidden">
                {activeTab === 'profile' && (
                    <div className="p-6 space-y-6">
                        <div className="grid grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                    <User className="w-4 h-4" />
                                    이름
                                </label>
                                <div className="px-4 py-3 bg-muted rounded-lg text-foreground">
                                    {displayName}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                    <Mail className="w-4 h-4" />
                                    이메일
                                </label>
                                <div className="px-4 py-3 bg-muted rounded-lg text-foreground">
                                    {email}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                    <Building className="w-4 h-4" />
                                    조직 ID
                                </label>
                                <div className="px-4 py-3 bg-muted rounded-lg text-foreground font-mono text-sm">
                                    {tenantId || '-'}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                    <Shield className="w-4 h-4" />
                                    역할
                                </label>
                                <div className="px-4 py-3 bg-muted rounded-lg">
                                    <span className="px-2 py-1 bg-primary/10 text-primary rounded-full text-sm font-medium">
                                        Admin
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'security' && (
                    <div className="p-6 space-y-6">
                        <div className="space-y-4">
                            <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
                                <div className="flex items-center gap-3">
                                    <Calendar className="w-5 h-5 text-muted-foreground" />
                                    <div>
                                        <div className="font-medium text-foreground">마지막 로그인</div>
                                        <div className="text-sm text-muted-foreground">지금</div>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
                                <div className="flex items-center gap-3">
                                    <Shield className="w-5 h-5 text-chart-2" />
                                    <div>
                                        <div className="font-medium text-foreground">인증 방식</div>
                                        <div className="text-sm text-muted-foreground">Microsoft Entra ID</div>
                                    </div>
                                </div>
                                <span className="px-2 py-1 bg-chart-2/10 text-chart-2 rounded-full text-xs font-medium">
                                    활성
                                </span>
                            </div>
                        </div>
                    </div>
                )}
            </Card>
        </div>
    )
}
