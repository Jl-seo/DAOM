import sys
from app.services.masking import mask_pii_data, _get_pii_paths
from app.schemas.model import _BaseExtractionModel, FieldDefinition
import json

model = _BaseExtractionModel(
    name="Test",
    description="Test",
    data_structure="json",
    fields=[
        FieldDefinition(key="name", label="Name", type="string", is_pii=True),
        FieldDefinition(key="contacts", label="Contacts", type="list", sub_fields=[
            {"key": "phone_number", "label": "Phone", "type": "string", "is_pii": True},
            {"key": "email", "label": "Email", "type": "string", "is_pii": False}
        ])
    ]
)

data = {
    "name": "Jeonglee Seo",
    "age": 30,
    "contacts": [
        {"phone_number": "010-1234-5678", "email": "test@test.com"},
        {"phone_number": "010-9876-5432", "email": "test2@test.com"}
    ]
}

print("Paths:", _get_pii_paths(model))
print("Original:", json.dumps(data, indent=2))
print("Masked:", json.dumps(mask_pii_data(data, model), indent=2))
