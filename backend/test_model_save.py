import asyncio
from app.schemas.model import ExtractionModelCreate, ExtractionModel, FieldDefinition
import uuid

def test():
    # Simulate DB model
    db_model = ExtractionModel(
        id=str(uuid.uuid4()),
        name="Test Model",
        fields=[FieldDefinition(key="name", label="Name")]
    )
    
    # Simulate frontend payload
    frontend_payload = {
        "id": db_model.id, # Frontend sends id even though it's omitted in Create
        "name": "Updated Model",
        "fields": [
            {"key": "name", "label": "Name Updated", "is_dex_target": True, "frontend_id": "temp-123"}
        ],
        "created_at": "2024-01-01T00:00:00Z",
        "beta_features": {
            "use_dex_validation": True,
            "use_optimized_prompt": False
        },
        "extra_field": "some value"
    }
    
    try:
        model_in = ExtractionModelCreate(**frontend_payload)
        print("ModelCreate parsed successfully")
    except Exception as e:
        print(f"Error parsing ExtractionModelCreate: {e}")
        return
        
    updated_dict = db_model.model_dump()
    model_in_dict = model_in.model_dump(exclude_unset=True)
    updated_dict.update(model_in_dict)
    
    try:
        updated_model = ExtractionModel(id=db_model.id, **updated_dict)
        print("Reconstructed ExtractionModel successfully")
        print(updated_model.model_dump())
    except Exception as e:
        print(f"Error reconstructing ExtractionModel: {e}")

if __name__ == "__main__":
    test()
