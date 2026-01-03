from enum import Enum

class ExtractionType(str, Enum):
    JOB = "extraction_job"
    LOG = "extraction_log"

class ExtractionStatus(str, Enum):
    # Processing states (P-Series)
    PENDING = "P100"       # Initial state
    UPLOADING = "P200"     # File uploading to storage
    ANALYZING = "P300"     # OCR / Doc Intelligence analysis
    REFINING = "P400"      # LLM processing / Refining
    # PREVIEW_READY (P500) - Deprecated, merged into SUCCESS
    
    # Success states (S-Series)
    SUCCESS = "S100"       # Completed successfully (auto)
    # CONFIRMED (S200) - Deprecated, merged into SUCCESS
    
    # Error states (E-Series)
    FAILED = "E100"        # Extraction failed
    ERROR = "E200"         # System error

class UserRole(str, Enum):
    SUPER_ADMIN = "SuperAdmin"
    SYSTEM_ADMIN = "System Admin"
    ADMIN = "Admin"
    MODEL_ADMIN = "ModelAdmin"
    USER = "User"
