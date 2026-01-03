from typing import Optional
from pydantic import BaseModel, Field

class StructuredData(BaseModel):
    merchantName: Optional[str] = Field(None, description="업체명 (상호)")
    businessLicenseNumber: Optional[str] = Field(None, description="사업자등록번호 (000-00-00000 또는 10자리 숫자)")
    date: Optional[str] = Field(None, description="거래 일자 (YYYY-MM-DD)")
    supplyValue: Optional[int] = Field(None, description="공급가액 (원 단위 정수)")
    surtax: Optional[int] = Field(None, description="부가세 (원 단위 정수, 공급가액의 10% 내외)")
    totalAmount: Optional[int] = Field(None, description="총금액 (공급가액 + 부가세)")

class ExtractionResponse(BaseModel):
    raw_text: str
    structured_data: StructuredData
