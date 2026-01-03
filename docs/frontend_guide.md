# Frontend Integration Guide for DAOM

This guide outlines how the Frontend Agent consumes data based on the shared schema.

## Type Definition (TypeScript)
Ensure your TypeScript interfaces match `shared/schema.json`.

```typescript
export type ProcessStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface DaomDocument {
  id: string; // UUID
  filename: string;
  uploadTimestamp: string; // ISO 8601
  status: ProcessStatus;
  unstructuredContent?: string;
  structuredData?: Record<string, any>; // Key-value pairs
  metadata?: Record<string, any>;
  errorMessage?: string;
}
```

## UI Behavior by Status
- **pending**: Show upload progress or queue state.
- **processing**: Show a loading spinner or processing animation.
- **completed**: Display `structuredData` in a form or table, and `unstructuredContent` in a view-only text area.
- **failed**: Display a red error alert with `errorMessage`.

## Schema Updates
If `shared/schema.json` is modified, regenerate these types to ensure type safety.
