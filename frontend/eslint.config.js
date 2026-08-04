import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'react',
              importNames: ['useEffect'],
              message: 'Direct useEffect is banned. Use render derivation, RTK Query, event handlers, key resets, or useMountEffect.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/shared/hooks/useMountEffect.ts'],
    rules: {
      'no-restricted-imports': 'off',
      'react-hooks/exhaustive-deps': 'off',
    },
  },
])
