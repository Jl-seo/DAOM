from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from app.schemas.model import ExtractionModel, ExtractionModelCreate
from app.services.models import load_models, save_models, get_model_by_id
from app.core.permissions import require_admin, verify_model_admin, verify_model_access, require_admin_or_model_admin
from app.services.audit import log_action, AuditAction, AuditResource
from app.core.auth import get_current_user, CurrentUser

import uuid
import logging
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter()

from app.core.auth import get_current_user, CurrentUser

@router.get("/", response_model=List[ExtractionModel])
async def list_models(current_user: CurrentUser = Depends(get_current_user)):
    # 1. Load active models
    all_models = [m for m in await load_models() if getattr(m, "is_active", True)]

    # 2. Check permissions
    from app.core.auth import is_super_admin
    from app.core.group_permission_utils import get_accessible_model_ids

    # Super Admin sees all
    if await is_super_admin(current_user):
        return all_models

    # Standard User / Model Admin sees only accessible models
    accessible_ids = await get_accessible_model_ids(
        current_user.id,
        current_user.tenant_id,
        access_token=getattr(current_user, 'access_token', None),
        user_groups=getattr(current_user, 'groups', None)
    )
    return [m for m in all_models if m.id in accessible_ids]

@router.post("/", response_model=ExtractionModel, dependencies=[Depends(require_admin)])
async def create_model(
    model_in: ExtractionModelCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    models = await load_models()
    new_model = ExtractionModel(
        id=str(uuid.uuid4()),
        **model_in.model_dump()
    )
    models.append(new_model)
    await save_models(models)

    # Audit: Model creation
    await log_action(
        user=current_user,
        action=AuditAction.CREATE_MODEL,
        resource_type=AuditResource.MODEL,
        resource_id=new_model.id,
        details={"model_name": new_model.name, "field_count": len(new_model.fields)},
        request=request
    )

    return new_model

@router.get("/{model_id}", response_model=ExtractionModel, dependencies=[Depends(verify_model_access)])
async def get_model(model_id: str):
    model = await get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model

@router.put("/{model_id}", response_model=ExtractionModel, dependencies=[Depends(verify_model_admin)])
async def update_model(
    model_id: str,
    model_in: ExtractionModelCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    """모델 업데이트"""
    models = await load_models()
    for i, m in enumerate(models):
        if m.id == model_id:
            # Preserve existing fields if not explicitly overridden by model_in
            updated_dict = m.model_dump()
            model_in_dict = model_in.model_dump(exclude_unset=True)
            
            # Explicitly preserve reference_data if it's NOT provided at all in model_in
            if "reference_data" not in model_in_dict:
                if m.reference_data is not None:
                    model_in_dict["reference_data"] = m.reference_data
                    
            updated_dict.update(model_in_dict)
            
            updated_model = ExtractionModel(
                **updated_dict
            )
            models[i] = updated_model
            await save_models(models)

            # Audit: Model update
            await log_action(
                user=current_user,
                action=AuditAction.UPDATE_MODEL,
                resource_type=AuditResource.MODEL,
                resource_id=model_id,
                details={"model_name": updated_model.name},
                request=request
            )

            return updated_model
    raise HTTPException(status_code=404, detail="Model not found")

@router.delete("/{model_id}", dependencies=[Depends(verify_model_admin)])
async def delete_model(
    model_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    models = await load_models()
    for i, m in enumerate(models):
        if m.id == model_id:
            # Soft delete
            updated_model = m.model_copy(update={"is_active": False})
            models[i] = updated_model
            await save_models(models)

            # Audit: Model deletion (soft delete)
            await log_action(
                user=current_user,
                action=AuditAction.DELETE_MODEL,
                resource_type=AuditResource.MODEL,
                resource_id=model_id,
                details={"model_name": m.name},
                request=request
            )

            return {"message": "Model deactivated"}

    raise HTTPException(status_code=404, detail="Model not found")

@router.get("/options/list", dependencies=[Depends(require_admin_or_model_admin)])
def list_model_options():
    """Get available Azure model types"""
    from app.services.doc_intel import get_supported_models
    return get_supported_models()

@router.get("/options/llms", dependencies=[Depends(require_admin_or_model_admin)])
async def list_llm_options():
    """Get available Azure OpenAI / API Foundry deployments"""
    from app.services.llm import fetch_available_models
    return await fetch_available_models()

@router.post("/analyze-sample", dependencies=[Depends(require_admin)])
async def analyze_sample(
    file: UploadFile = File(...),
    model_type: str = Form("prebuilt-layout")
):
    """
    Analyze a sample document using Azure Doc Intelligence 
    and return a list of suggested fields (schema).
    """
    from app.services import doc_intel

    # 1. Read file bytes
    file_bytes = await file.read()

    try:
        # 2. Run analysis (pass bytes + filename for MIME detection)
        result = await doc_intel.extract_with_strategy(file_bytes, model_type, filename=file.filename)

        # 3. Heuristic Field Discovery
        suggested_fields = []
        seen_keys = set()

        # Strategy A: Key-Value Pairs (common in Forms)
        if "key_value_pairs" in result:
            for kv in result["key_value_pairs"]:
                key = kv.get("key", "").strip()
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    suggested_fields.append({
                        "key": key,
                        "label": key,
                        "type": "string",
                        "description": f"Detected from Key-Value Pair. Sample: {kv.get('value')}"
                    })

        # Strategy B: Table Headers (common in Invoices/Tables)
        if "tables" in result:
            for table in result["tables"]:
                # Assume first row is header
                headers = [
                    c.get("content") for c in table.get("cells", [])
                    if c.get("row_index") == 0
                ]
                for h in headers:
                    h_clean = h.strip()
                    if h_clean and h_clean not in seen_keys:
                        seen_keys.add(h_clean)
                        suggested_fields.append({
                            "key": h_clean,
                            "label": h_clean,
                            "type": "string",
                            "description": "Detected from Table Header"
                        })

        # Strategy C: Prebuilt Fields (Documents)
        if "documents" in result:
             for doc in result["documents"]:
                for field_name, field_data in doc.get("fields", {}).items():
                     if field_name not in seen_keys:
                        seen_keys.add(field_name)
                        suggested_fields.append({
                            "key": field_name,
                            "label": field_name,
                            "type": field_data.get("type", "string"), # e.g. currency, date
                            "description": f"Prebuilt Field. Sample: {field_data.get('value')}"
                        })

        # --- LLM Refinement Step ---
        # If model is generic layout/read, OR if heuristic produced few results, use LLM
        if model_type in ["prebuilt-layout", "prebuilt-read"] or len(suggested_fields) < 3:
            try:
                from app.services import llm
                content = result.get("content", "")
                tables = result.get("tables", [])

                llm_fields = await llm.generate_schema_from_content(content, tables)

                if llm_fields and len(llm_fields) > 0:
                    # User requested "Processed by LLM only".
                    # So if LLM succeeds, we discard the "noisy" raw heuristics (Strategy A/B)
                    # We might want to keep 'Prebuilt' (Strategy C) if it was Invoice/Receipt,
                    # but for Layout/Read, LLM is definitely better.
                    suggested_fields = llm_fields
                else:
                     # Fallback to merge if LLM returned nothing
                     pass

            except Exception as llm_error:
                logger.warning(f"LLM Enrichment failed: {llm_error}")
                # Continue with just heuristic fields

        return {
            "fields": suggested_fields,
            "raw_result": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schema/refine", dependencies=[Depends(require_admin)])
async def refine_schema_endpoint(
    payload: dict = {
        "fields": [],
        "instruction": ""
    }
):
    """
    Refine schema based on natural language instruction
    """
    from app.services import llm

    fields = payload.get("fields", [])
    instruction = payload.get("instruction", "")

    if not instruction:
        return {"fields": fields}

    try:
        refined_fields = await llm.refine_schema(fields, instruction)
        return {"fields": refined_fields}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
