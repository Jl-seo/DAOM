// DAOM i18n Configuration
// This file exports locale data for internationalization

export const locales = ['ko', 'en'] as const
export type Locale = typeof locales[number]

export const defaultLocale: Locale = 'ko'

// Locale display names
export const localeNames: Record<Locale, string> = {
    ko: '한국어',
    en: 'English'
}

// Import locale files
import ko from './locales/ko.json'
import en from './locales/en.json'

export const translations = { ko, en }

// Type-safe translation accessor
export type TranslationKeys = typeof ko

/**
 * Usage example with react-i18next:
 * 
 * 1. Install: npm install i18next react-i18next
 * 2. Initialize:
 *    import i18n from 'i18next'
 *    import { initReactI18next } from 'react-i18next'
 *    import { translations, defaultLocale } from '@/i18n'
 * 
 *    i18n.use(initReactI18next).init({
 *      resources: {
 *        ko: { translation: translations.ko },
 *        en: { translation: translations.en }
 *      },
 *      lng: defaultLocale,
 *      fallbackLng: 'en'
 *    })
 * 
 * 3. Use in components:
 *    const { t } = useTranslation()
 *    <button>{t('common.actions.save')}</button>
 */
