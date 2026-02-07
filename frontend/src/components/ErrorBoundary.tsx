import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { AlertTriangle, Home, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
    children: ReactNode
    fallback?: ReactNode
}

interface State {
    hasError: boolean
    error: Error | null
    errorInfo: ErrorInfo | null
}

/**
 * Error Boundary for catching React rendering errors
 * Prevents entire app crashes and shows user-friendly error UI
 */
export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props)
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null
        }
    }

    static getDerivedStateFromError(error: Error): Partial<State> {
        return { hasError: true, error }
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo)
        this.setState({
            error,
            errorInfo
        })
    }

    handleReset = () => {
        this.setState({
            hasError: false,
            error: null,
            errorInfo: null
        })
    }

    handleGoHome = () => {
        window.location.href = '/models'
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback
            }

            return (
                <div className="min-h-screen flex items-center justify-center bg-background p-4">
                    <div className="max-w-md w-full text-center">
                        <div className="w-16 h-16 mx-auto mb-6 bg-destructive/10 rounded-full flex items-center justify-center">
                            <AlertTriangle className="w-8 h-8 text-destructive" />
                        </div>

                        <h1 className="text-2xl font-bold text-foreground mb-2">
                            문제가 발생했습니다
                        </h1>

                        <p className="text-muted-foreground mb-6">
                            페이지를 표시하는 중 오류가 발생했습니다.
                            다시 시도하거나 홈으로 이동해주세요.
                        </p>

                        {import.meta.env.DEV && this.state.error && (
                            <details className="mb-6 text-left">
                                <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                                    개발자 정보 보기
                                </summary>
                                <div className="mt-2 p-4 bg-muted rounded-lg text-xs font-mono overflow-auto max-h-48">
                                    <div className="text-destructive font-bold mb-2">
                                        {this.state.error.message}
                                    </div>
                                    {this.state.errorInfo && (
                                        <pre className="whitespace-pre-wrap text-muted-foreground">
                                            {this.state.errorInfo.componentStack}
                                        </pre>
                                    )}
                                </div>
                            </details>
                        )}

                        <div className="flex gap-3 justify-center">
                            <Button
                                variant="outline"
                                onClick={this.handleReset}
                                className="gap-2"
                            >
                                <RefreshCw className="w-4 h-4" />
                                다시 시도
                            </Button>
                            <Button
                                onClick={this.handleGoHome}
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

        return this.props.children
    }
}
