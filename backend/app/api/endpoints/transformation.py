from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.transformation.parser import RuleParser
from app.services.transformation.engine import TransformationEngine, TransformationRule

router = APIRouter()

class ParseRequest(BaseModel):
    text: str
    available_fields: List[str]

class ParseResponse(BaseModel):
    rules: List[Dict[str, Any]]

class TestRequest(BaseModel):
    rules: List[Dict[str, Any]]
    sample_data: Dict[str, Any]

class TestResponse(BaseModel):
    result: Dict[str, Any]
    audit: List[Dict[str, Any]]

@router.post("/parse", response_model=ParseResponse)
async def parse_rules(req: ParseRequest):
    parser = RuleParser()
    rules = await parser.parse_natural_language(req.text, req.available_fields)
    return {"rules": [r.dict() for r in rules]}

@router.post("/test", response_model=TestResponse)
async def test_rules(req: TestRequest):
    engine = TransformationEngine()
    # Convert dicts back to TransformationRule objects
    rules_objs = [TransformationRule(**r) for r in req.rules]

    result = engine.apply(req.sample_data, rules_objs)

    return {
        "result": result["processed"],
        "audit": result["audit"]
    }
