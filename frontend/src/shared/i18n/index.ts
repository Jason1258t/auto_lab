// All UI texts go through i18next (decided 2026-10-07): English only for
// now, but adding Russian later means adding ru.json and a language
// switch, with no change to the components.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en.json'

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
})

export default i18n
