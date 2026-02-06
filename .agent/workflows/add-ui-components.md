---
description: How to add new shadcn/ui components or create custom components
---

# Adding UI Components

## Using shadcn/ui Components

### 1. Check Available Components
```bash
# turbo
npx shadcn@latest list
```

### 2. Add New Component
```bash
# turbo
cd frontend
npx shadcn@latest add [component-name]
```
Example: `npx shadcn@latest add tooltip`

### 3. Component Location
Components are added to `frontend/src/components/ui/`

---

## Creating Custom Components

### 1. File Naming
- Component file: `ComponentName.tsx`
- Use PascalCase for component names
- Place in appropriate directory:
  - `components/` - Shared components
  - `components/ui/` - Base UI primitives
  - `features/[feature]/components/` - Feature-specific

### 2. Component Structure
```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

interface ComponentNameProps {
  onAction?: () => void
}

export function ComponentName({ onAction }: ComponentNameProps) {
  const { t } = useTranslation()
  // ...
}
```

### 3. Export Pattern
```tsx
// Named export (preferred for components)
export function ComponentName() {}

// Default export (for pages)
export default function PageName() {}
```

---

## Icon Usage

### Lucide Icons (Preferred)
```tsx
import { FileText, Loader2, ChevronRight } from 'lucide-react'

<FileText className="w-5 h-5" />
<Loader2 className="w-5 h-5 animate-spin" />
```

### Common Icon Sizes
- `w-4 h-4` - Inline/button icons
- `w-5 h-5` - Standard icons
- `w-6 h-6` - Emphasis icons
- `w-8 h-8` - Large/hero icons

---

## Styling Patterns

### Use Tailwind Classes
```tsx
// ✓ Good
<div className="flex items-center gap-2 p-4 bg-muted rounded-lg">

// ✗ Avoid inline styles
<div style={{ display: 'flex' }}>
```

### Use CSS Variables for Theme
```tsx
// ✓ Uses theme colors
<div className="bg-primary text-primary-foreground">
<div className="bg-muted text-muted-foreground">
<div className="border-border">
```

### Responsive Design
```tsx
// Mobile-first
<div className="flex flex-col md:flex-row lg:grid lg:grid-cols-3">
```
