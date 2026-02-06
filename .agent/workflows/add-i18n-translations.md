---
description: How to add new i18n translations for Korean, English, etc.
---

# Adding i18n Translations

## File Locations
```
frontend/public/locales/
├── en/translation.json
├── ko/translation.json
├── ja/translation.json (if exists)
└── tw/translation.json (if exists)
```

## 1. Add Translation Key
Add to ALL locale files to avoid missing translations:

```json
// ko/translation.json
{
  "feature": {
    "new_label": "새 기능"
  }
}

// en/translation.json
{
  "feature": {
    "new_label": "New Feature"
  }
}
```

## 2. Use in Component
```tsx
import { useTranslation } from 'react-i18next'

function Component() {
  const { t } = useTranslation()
  return <span>{t('feature.new_label')}</span>
}
```

## 3. Verification
```bash
# Check for missing keys across locales
diff <(jq -r 'paths | join(".")' ko/translation.json | sort) \
     <(jq -r 'paths | join(".")' en/translation.json | sort)
```

## Common Mistakes
| Mistake | Fix |
|---------|-----|
| Hardcoded Korean text | Use `t('key')` |
| Key exists in ko but not en | Add to all locales |
| Using template literals | Use `t('key', { value })` with interpolation |
