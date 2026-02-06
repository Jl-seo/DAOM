---
description: Pre-deployment checklist for backend and frontend
---

# Deployment Verification Checklist

## Backend Verification

### 1. Syntax Check
```bash
# turbo
cd backend
python -c "
import ast
import glob
for f in glob.glob('app/**/*.py', recursive=True):
    ast.parse(open(f).read())
    print(f'✓ {f}')
"
```

### 2. Import Check
```bash
# turbo
cd backend
python -c "from app.main import app; print('✓ Main app imports OK')"
```

### 3. Environment Variables
Ensure all required env vars are set:
- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_CLIENT_ID` / `AZURE_TENANT_ID`

---

## Frontend Verification

### 1. Build Check
```bash
# turbo
cd frontend
npm run build
```

### 2. Type Check (if build passes, this is implied)
```bash
# turbo
cd frontend
npx tsc --noEmit
```

### 3. Environment Variables
Check `.env.production`:
- `VITE_API_BASE_URL`
- `VITE_AZURE_CLIENT_ID`
- `VITE_AZURE_TENANT_ID`

---

## Integration Check

### 1. API Endpoints Match
```bash
# Compare backend routes with frontend api.ts
grep -o "'/[^']*'" backend/app/api/endpoints/*.py | sort -u
grep -o "'/[^']*'" frontend/src/lib/api.ts | sort -u
```

### 2. Permission Sync
- [ ] Backend permission checks match frontend UI visibility
- [ ] All new endpoints have corresponding api.ts methods

---

## Post-Deployment

- [ ] Verify login flow works
- [ ] Test extraction on sample document
- [ ] Check admin panel access
- [ ] Verify audit logs are recording
