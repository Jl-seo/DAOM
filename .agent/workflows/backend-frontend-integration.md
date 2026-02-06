---
description: Backend-Frontend integration checklist to avoid missing connections
---

# Backend-Frontend Integration Checklist

Follow this checklist whenever implementing features that span backend and frontend.

## When Adding New Backend API Endpoints

1. **Backend: Create Endpoint**
   - Add route in `backend/app/api/endpoints/`
   - Define request/response Pydantic models
   - Add to router in `__init__.py`

2. **Frontend: Add API Method** (REQUIRED)
   - [ ] Add API method in `frontend/src/lib/api.ts`
   - [ ] Define TypeScript types for request/response

3. **Frontend: UI Integration** (REQUIRED)
   - [ ] Create or update component to call the API
   - [ ] Add loading state handling
   - [ ] Add error state handling
   - [ ] Add success/error toast notifications

4. **Frontend: Context/State** (if applicable)
   - [ ] Update `AuthContext.tsx` if permission-related
   - [ ] Add to React Query cache if data needs auto-refresh

---

## When Adding Permission Features

| Layer | Action |
|-------|--------|
| Backend | Add permission check in API endpoint |
| Frontend api.ts | Add API method |
| AuthContext | Fetch user permissions on login |
| UI Components | Filter/hide elements based on permissions |

### Permission Flow Example
```
1. Backend: GET /menus/accessible → returns only accessible menus
2. api.ts: menusApi.getAccessible() 
3. AuthContext: fetch accessible menus, store in state
4. Sidebar.tsx: filter menus based on accessibleMenus from context
```

---

## When Adding Bulk Operations

1. **Backend**: Create batch endpoint with pagination/chunking
2. **Frontend**: Create dedicated component (e.g., `BulkUserImport.tsx`)
3. **UI**: Add toggle button in parent component
4. **UX**: Include file template download, preview, and progress indication

---

## When Adding New Menu/Page

1. [ ] Add menu item to backend menus collection
2. [ ] Add route in `App.tsx`
3. [ ] Add menu item in `Sidebar.tsx`
4. [ ] Add menu permission in group permissions UI

---

## Verification Commands

```bash
# Check if frontend API has corresponding backend endpoint
grep -r "endpoint-name" frontend/src/lib/api.ts
grep -r "apiMethod" frontend/src/

# Check if UI uses context values  
grep -r "useAuth" frontend/src/components/

# Build test
cd frontend && npm run build

# Backend syntax check
python -c "import ast; ast.parse(open('backend/app/file.py').read())"
```

---

## Common Mistakes to Avoid

| Mistake | Prevention |
|---------|------------|
| Backend endpoint exists but no api.ts method | Always add to api.ts immediately after creating endpoint |
| Permission added to backend but UI not filtered | Check AuthContext and component visibility logic |
| New field added to backend model but not TypeScript type | Update both Model.py and types/model.ts |
| CSV import backend done but no UI | Create dedicated import component |
| Menu permission backend done but Sidebar not filtered | Add accessibleMenus to AuthContext and filter in Sidebar |
