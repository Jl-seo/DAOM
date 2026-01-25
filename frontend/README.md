# DAOM Frontend

Daom (Doc Analysis & Object Mapper) Frontend Application built with React, Vite, and Tailwind CSS.

## 🚀 Environment Configuration

### Authentication (Important for Guest Users)
To enable **Azure AD Guest Login** (B2B), you must explicitly configure the Host Tenant ID.
If this is missing, the app defaults to `common`, which forces users to login to their home tenant, causing access errors for guest accounts.

**Required Environment Variable:**
```bash
VITE_AZURE_TENANT_ID=your-company-tenant-uuid
```
*In GitHub Actions/Deployment, set this via `AZURE_TENANT_ID` secret.*

## ✨ Features & Usage Guide

### 1. Comparison Analysis Settings
You can customize the comparison behavior in **Model Settings**:
- **Output Language**: Defines the language of AI-generated descriptions (e.g., "Korean", "English").
- **Noise Filtering**: Automatically ignores compression artifacts, anti-aliasing, and minor position shifts.
  - Options: `Ignore Color Changes`, `Ignore Position Shifts`, etc.

### 2. Excel Export
- **Candidate Column**: Automatically displays the **filename** extracted from the uploaded URL.
- **Key Safety**: The Data Key in Excel Settings is now **Read-Only** to prevent configuration errors. Only Labels and Widths can be modified.

### 3. Localization (i18n)
- Supports dynamic switching (Korean/English).
- UI Text and API Error messages are localized.

## 🛠 Deployment
Builds are handled via GitHub Actions (`deploy-frontend.yml`).
Make sure to set `AZURE_TENANT_ID` to support guest logins.
