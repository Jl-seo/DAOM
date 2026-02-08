import { useState } from 'react'
import { useSiteConfig } from '../SiteConfigProvider'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Building2, Image, Type, Save } from 'lucide-react'
import { toast } from 'sonner'

export function BrandingEditor() {
    const { config, updateConfig } = useSiteConfig()
    const [siteName, setSiteName] = useState(config.siteName)
    const [siteDescription, setSiteDescription] = useState(config.siteDescription)
    const [logoUrl, setLogoUrl] = useState(config.logoUrl || '')
    const [hasChanges, setHasChanges] = useState(false)

    const handleSave = async () => {
        await updateConfig({
            siteName,
            siteDescription,
            logoUrl: logoUrl || undefined
        })
        setHasChanges(false)
        toast.success('브랜딩 설정이 저장되었습니다')
    }

    const handleChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
        setter(e.target.value)
        setHasChanges(true)
    }

    return (
        <div className="space-y-6">
            {/* Site Name */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Type className="w-4 h-4" />
                        서비스 이름
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div>
                        <label className="text-sm font-medium text-muted-foreground mb-2 block">
                            서비스 이름
                        </label>
                        <Input
                            value={siteName}
                            onChange={handleChange(setSiteName)}
                            placeholder="예: DAOM"
                        />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-muted-foreground mb-2 block">
                            서비스 설명
                        </label>
                        <Input
                            value={siteDescription}
                            onChange={handleChange(setSiteDescription)}
                            placeholder="예: 문서 자동화"
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Logo */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Image className="w-4 h-4" />
                        로고
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div>
                        <label className="text-sm font-medium text-muted-foreground mb-2 block">
                            로고 업로드 (또는 URL 입력)
                        </label>
                        <div className="flex gap-2">
                            <Button variant="outline" onClick={() => document.getElementById('logo-upload')?.click()}>
                                <Image className="w-4 h-4 mr-2" />
                                파일 선택
                            </Button>
                            <Input
                                id="logo-upload"
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) {
                                        // Quick implementation: Base64 or Object URL for now?
                                        // For persistence in simple config, Base64 is okay for small logos.
                                        // Or better, trigger an upload API.
                                        // Given no specific upload endpoint for logos, we use Base64 to save in JSON config directly.
                                        const reader = new FileReader();
                                        reader.onloadend = () => {
                                            setLogoUrl(reader.result as string);
                                            setHasChanges(true);
                                        };
                                        reader.readAsDataURL(file);
                                    }
                                }}
                            />
                        </div>
                        <div className="mt-2">
                            <Input
                                value={logoUrl}
                                onChange={handleChange(setLogoUrl)}
                                placeholder="https://example.com/logo.png"
                            />
                        </div>
                    </div>

                    {/* Preview */}
                    <div className="p-4 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground mb-3">미리보기</p>
                        <div className="flex items-center gap-3">
                            {logoUrl ? (
                                <img
                                    src={logoUrl}
                                    alt="Logo preview"
                                    className="w-10 h-10 rounded-lg object-contain bg-background"
                                    onError={(e) => {
                                        (e.target as HTMLImageElement).style.display = 'none'
                                    }}
                                />
                            ) : (
                                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center">
                                    <Building2 className="w-5 h-5 text-primary-foreground" />
                                </div>
                            )}
                            <div>
                                <div className="font-bold text-foreground">{siteName || 'DAOM'}</div>
                                <div className="text-xs text-muted-foreground">{siteDescription || '문서 자동화'}</div>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Save Button */}
            {hasChanges && (
                <Button onClick={handleSave} className="w-full">
                    <Save className="w-4 h-4 mr-2" />
                    변경사항 저장
                </Button>
            )}
        </div>
    )
}
