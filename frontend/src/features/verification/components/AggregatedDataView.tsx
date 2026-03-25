import { useState, useEffect } from 'react'
import { ArrowLeft, Download, Loader2, Table as TableIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api'
import type { ExtractionModel } from '../types'
import { format } from 'date-fns'
import * as XLSX from 'xlsx'

interface AggregatedDataViewProps {
    model: ExtractionModel
    onBack: () => void
}

export function AggregatedDataView({ model, onBack }: AggregatedDataViewProps) {
    const [data, setData] = useState<any[]>([])
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        const fetchData = async () => {
            try {
                setIsLoading(true)
                const res = await apiClient.get(`/extraction/logs/aggregated/${model.id}`)
                setData(res.data)
            } catch (error) {
                console.error('Failed to fetch aggregated data:', error)
                toast.error('통합 데이터를 불러오는데 실패했습니다.')
            } finally {
                setIsLoading(false)
            }
        }
        fetchData()
    }, [model.id])

    // Extract all unique column keys from the data to build the table header
    const columns = data.length > 0
        ? Array.from(new Set(data.flatMap(Object.keys))).filter(
              k => !['_log_id', '_document_name', '_created_at'].includes(k)
          )
        : []

    const getCellValue = (val: any): string => {
        if (val === null || val === undefined) return ''
        if (typeof val === 'object' && val !== null) {
            if ('value' in val) return String(val.value)
            // fallback if it's an array or some other object
            try { return JSON.stringify(val) } catch { return String(val) }
        }
        return String(val)
    }

    const handleExportExcel = () => {
        if (!data.length) {
            toast.error('내보낼 데이터가 없습니다.')
            return
        }

        try {
            // Re-order keys for the Excel export too
            const exportData = data.map(row => {
                const orderedRow: Record<string, any> = {}
                orderedRow['파일명'] = row['_document_name']
                orderedRow['추출일시'] = row['_created_at'] ? format(new Date(row['_created_at']), 'yyyy-MM-dd HH:mm') : ''
                
                columns.forEach(col => {
                    orderedRow[col] = getCellValue(row[col])
                })
                return orderedRow
            })

            const worksheet = XLSX.utils.json_to_sheet(exportData)
            const workbook = XLSX.utils.book_new()
            XLSX.utils.book_append_sheet(workbook, worksheet, 'Aggregated Data')
            XLSX.writeFile(workbook, `[DAOM] ${model.name}_통합데이터_${format(new Date(), 'yyyyMMdd_HHmm')}.xlsx`)
            
            toast.success('엑셀 다운로드가 완료되었습니다.')
        } catch (error) {
            console.error('Export failed', error)
            toast.error('엑셀 내보내기 중 오류가 발생했습니다.')
        }
    }

    return (
        <div className="flex-1 flex flex-col min-h-0 bg-muted/30 p-4 md:p-8">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <Button variant="ghost" onClick={onBack} className="mb-2 -ml-4 hover:bg-transparent text-muted-foreground">
                        <ArrowLeft className="w-4 h-4 mr-2" /> 뒤로가기
                    </Button>
                    <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-3">
                        <TableIcon className="w-6 h-6 text-primary" />
                        통합 데이터 모아보기
                        <Badge variant="secondary" className="text-sm font-normal">
                            {model.name}
                        </Badge>
                    </h1>
                    <p className="text-muted-foreground mt-2">이 모델로 성공적으로 추출된 모든 문서의 매핑 결과를 합쳐서 봅니다.</p>
                </div>
                <Button 
                    onClick={handleExportExcel} 
                    disabled={isLoading || data.length === 0}
                    className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg transition-all"
                >
                    <Download className="w-4 h-4 mr-2" />
                    엑셀 다운로드 (Export)
                </Button>
            </div>

            <Card className="flex-1 flex flex-col min-h-0 shadow-sm border-muted">
                <CardHeader className="py-4 border-b bg-card shrink-0 flex flex-row items-center justify-between">
                    <div>
                        <CardTitle className="text-lg">글로벌 매핑 레코드</CardTitle>
                        <CardDescription>총 {data.length}개의 데이터 행(Row)이 병합되었습니다.</CardDescription>
                    </div>
                </CardHeader>
                <CardContent className="flex-1 p-0 overflow-auto relative">
                    {isLoading ? (
                        <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/50 backdrop-blur-sm z-10">
                            <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
                            <p className="text-muted-foreground">대량의 데이터를 병합 중입니다...</p>
                        </div>
                    ) : data.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 text-center">
                            <TableIcon className="w-12 h-12 mb-4 text-muted" />
                            <p className="text-lg font-medium mb-1">통합할 데이터가 없습니다</p>
                            <p>성공적으로 매핑된 추출 내역이 없거나 내보내기 설정이 없습니다.</p>
                        </div>
                    ) : (
                        <div className="w-full relative h-full">
                            <Table className="whitespace-nowrap">
                                <TableHeader className="bg-muted/50 sticky top-0 z-10 shadow-sm">
                                    <TableRow>
                                        <TableHead className="font-semibold px-4 w-[200px]">파일명</TableHead>
                                        <TableHead className="font-semibold px-4 w-[160px]">추출일시</TableHead>
                                        {columns.map(col => (
                                            <TableHead key={col} className="font-semibold px-4">{col}</TableHead>
                                        ))}
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {data.map((row, idx) => (
                                        <TableRow key={idx} className="hover:bg-muted/30 transition-colors">
                                            <TableCell className="px-4 font-medium text-foreground truncate max-w-[200px]" title={row['_document_name']}>
                                                {row['_document_name']}
                                            </TableCell>
                                            <TableCell className="px-4 text-muted-foreground">
                                                {row['_created_at'] ? format(new Date(row['_created_at']), 'MM-dd HH:mm') : '-'}
                                            </TableCell>
                                            {columns.map((col) => (
                                                <TableCell key={col} className="px-4">
                                                    {getCellValue(row[col]) || '-'}
                                                </TableCell>
                                            ))}
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
