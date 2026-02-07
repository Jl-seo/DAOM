import { useNavigate } from 'react-router-dom'
import { FileQuestion, Home, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * 404 Not Found Page
 * Displayed when user navigates to an invalid route
 */
export function NotFoundPage() {
    const navigate = useNavigate()

    return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
            <div className="max-w-md w-full text-center">
                <div className="w-20 h-20 mx-auto mb-6 bg-primary/10 rounded-full flex items-center justify-center">
                    <FileQuestion className="w-10 h-10 text-primary" />
                </div>

                <h1 className="text-6xl font-bold text-foreground mb-2">
                    404
                </h1>

                <h2 className="text-2xl font-semibold text-foreground mb-3">
                    페이지를 찾을 수 없습니다
                </h2>

                <p className="text-muted-foreground mb-8">
                    요청하신 페이지가 존재하지 않거나 이동되었습니다.
                    URL을 확인하시거나 홈으로 돌아가주세요.
                </p>

                <div className="flex gap-3 justify-center">
                    <Button
                        variant="outline"
                        onClick={() => navigate(-1)}
                        className="gap-2"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        뒤로 가기
                    </Button>
                    <Button
                        onClick={() => navigate('/models')}
                        className="gap-2"
                    >
                        <Home className="w-4 h-4" />
                        홈으로 이동
                    </Button>
                </div>
            </div>
        </div>
    )
}
