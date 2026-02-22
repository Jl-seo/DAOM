import React, { useEffect, useRef, useState } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Camera, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api';
import { type ExtractionModel } from '../types';

interface DEXScannerProps {
    model: ExtractionModel;
    onClose: () => void;
}

export const DEXScanner: React.FC<DEXScannerProps> = ({ model, onClose }) => {
    const [scannerActive, setScannerActive] = useState(false);
    const [scanState, setScanState] = useState<'IDLE' | 'LOADING' | 'PASS' | 'FAIL'>('IDLE');
    const [resultData, setResultData] = useState<{ barcode?: string, name?: string, lisName?: string, errorMsg?: string }>({});

    // Using a ref to track the scanner instance
    const html5QrCode = useRef<Html5Qrcode | null>(null);
    const videoRef = useRef<HTMLDivElement>(null);

    const startScanner = async () => {
        if (!videoRef.current) return;

        try {
            setScannerActive(true);
            setScanState('IDLE');
            setResultData({});

            html5QrCode.current = new Html5Qrcode("dex-reader");

            await html5QrCode.current.start(
                { facingMode: "environment" },
                {
                    fps: 10,
                    qrbox: { width: 300, height: 150 },
                    aspectRatio: 1.0
                },
                (decodedText, _decodedResult) => {
                    // Stop scanning immediately on first hit
                    if (html5QrCode.current?.isScanning) {
                        html5QrCode.current.pause();
                        handleBarcodeSuccess(decodedText);
                    }
                },
                (_errorMessage) => {
                    // Background noise (parsing errors), ignore
                }
            );
        } catch (error) {
            console.error("Scanner init error:", error);
            setScannerActive(false);
        }
    };

    const stopScanner = async () => {
        if (html5QrCode.current?.isScanning) {
            try {
                await html5QrCode.current.stop();
                setScannerActive(false);
            } catch (err) { }
        }
    };

    const handleBarcodeSuccess = async (text: string) => {
        setScanState('LOADING');
        setResultData({ barcode: text });

        // Step 1: Attempt to crop via the underlying video element if available.
        // html5-qrcode creates a <video> element inside the div.
        try {
            const videoElem = document.querySelector('#dex-reader video') as HTMLVideoElement;
            let blobToSend: Blob | null = null;

            if (videoElem) {
                const canvas = document.createElement('canvas');
                // Capture the entire frame for the backend DI process
                canvas.width = videoElem.videoWidth;
                canvas.height = videoElem.videoHeight;
                const ctx = canvas.getContext('2d');
                if (ctx) {
                    ctx.drawImage(videoElem, 0, 0, canvas.width, canvas.height);

                    // Convert to JPG blob aiming for < 100KB
                    blobToSend = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.8));
                }
            }

            if (!blobToSend) {
                throw new Error("비디오 프레임 추출에 실패했습니다.");
            }

            // Step 2: Send Blob & Barcode to Backend DEX API
            const targetField = model.fields?.[0]?.label || '환자 성명';
            const formData = new FormData();
            formData.append('cropped_image', blobToSend, 'capture.jpg');
            formData.append('barcode_value', text);
            formData.append('model_id', model.id);
            formData.append('target_field', targetField);

            const response = await apiClient.post('/extraction/dex-validate', formData);
            const res = response as any;

            if (res.is_match) {
                setScanState('PASS');
                setResultData({
                    barcode: text,
                    name: res.handwritten_name,
                    lisName: res.lis_name
                });
            } else {
                setScanState('FAIL');
                setResultData({
                    barcode: text,
                    name: res.handwritten_name,
                    lisName: res.lis_name,
                    errorMsg: `불일치 발생: 수기 ${targetField} '${res.handwritten_name}'과 LIS 등록 이름 '${res.lis_name}'가 일치하지 않습니다.`
                });
            }

        } catch (error: any) {
            setScanState('FAIL');
            setResultData(prev => ({
                ...prev,
                errorMsg: error.response?.data?.detail || error.message || "DEX 검증 서버 통신 실패"
            }));
        }
    };

    const resetScan = () => {
        setScanState('IDLE');
        setResultData({});
        if (html5QrCode.current) {
            html5QrCode.current.resume();
        } else {
            startScanner();
        }
    };

    useEffect(() => {
        return () => {
            stopScanner();
        };
    }, []);

    return (
        <div className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center p-4">

            <div className="w-full max-w-lg bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col">
                <div className="p-4 bg-slate-100 flex items-center justify-between border-b">
                    <div>
                        <h3 className="font-semibold text-lg flex items-center">
                            <Camera className="w-5 h-5 mr-2 text-primary" />
                            DEX 실시간 교차 검증 (Beta)
                        </h3>
                        <p className="text-sm text-slate-500">라벨의 바코드와 {model.fields?.[0]?.label || '환자 성명'}을 스캔합니다.</p>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => { stopScanner(); onClose(); }}>
                        <X className="w-6 h-6" />
                    </Button>
                </div>

                {/* Video Area */}
                <div className="relative bg-black w-full" style={{ minHeight: '300px' }}>

                    {!scannerActive && (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <Button onClick={startScanner} size="lg" className="bg-primary shadow-lg animate-pulse">
                                카메라 활성화
                            </Button>
                        </div>
                    )}

                    <div id="dex-reader" ref={videoRef} className="w-full h-full object-cover"></div>

                    {/* Progress Overlays */}
                    {scanState === 'LOADING' && (
                        <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-white backdrop-blur-sm">
                            <Loader2 className="w-12 h-12 animate-spin mb-4 text-blue-400" />
                            <h4 className="text-xl font-bold">인식 중...</h4>
                            <p className="text-sm opacity-80 mt-2">바코드: {resultData.barcode}</p>
                            <p className="text-sm opacity-80">Azure DI 수기 분석 중...</p>
                        </div>
                    )}

                    {scanState === 'PASS' && (
                        <div className="absolute inset-0 bg-green-500/80 flex flex-col items-center justify-center text-white animate-in fade-in zoom-in duration-300">
                            <CheckCircle2 className="w-20 h-20 mb-4 drop-shadow-lg" />
                            <h4 className="text-3xl font-bold drop-shadow-md">검증 완료</h4>
                            <p className="text-lg mt-2 font-medium drop-shadow">환자명 확인: {resultData.name} (일치)</p>
                            <p className="opacity-80 mt-1">바코드: {resultData.barcode}</p>
                            <Button onClick={resetScan} className="mt-6 bg-white text-green-700 hover:bg-slate-100">
                                다음 검체 스캔
                            </Button>
                        </div>
                    )}
                </div>

                {/* Status Bar / Extracted Info */}
                <div className="p-4 bg-white min-h-[120px]">
                    {scanState === 'IDLE' && (
                        <div className="h-full flex flex-col items-center justify-center text-slate-500">
                            <p>수기 이름과 바코드가 화면에 들어오도록 기기를 위치해주세요.</p>
                        </div>
                    )}

                    {scanState === 'FAIL' && (
                        <Alert variant="destructive" className="animate-in slide-in-from-bottom-2">
                            <AlertCircle className="h-4 w-4" />
                            <AlertTitle>불일치 및 검증 실패</AlertTitle>
                            <AlertDescription>
                                {resultData.errorMsg}
                                <div className="mt-3 flex justify-end">
                                    <Button variant="outline" size="sm" onClick={resetScan} className="border-red-500 text-red-600 hover:bg-red-50">
                                        재시도
                                    </Button>
                                </div>
                            </AlertDescription>
                        </Alert>
                    )}
                </div>

            </div>
        </div>
    );
};
