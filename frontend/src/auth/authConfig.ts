import { LogLevel } from '@azure/msal-browser'
import type { Configuration } from '@azure/msal-browser'

// Azure AD App Registration Client ID
const AZURE_CLIENT_ID = '689d0170-0576-4563-8a24-a323625196ca'

// Multi-tenant: Use 'common' to accept any organization
const AZURE_AUTHORITY = 'https://login.microsoftonline.com/common'

export const msalConfig: Configuration = {
    auth: {
        clientId: AZURE_CLIENT_ID,
        authority: AZURE_AUTHORITY,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
        navigateToLoginRequestUrl: true
    },
    cache: {
        cacheLocation: 'localStorage',
        storeAuthStateInCookie: false
    },
    system: {
        loggerOptions: {
            loggerCallback: (level, message, containsPii) => {
                if (containsPii) return
                switch (level) {
                    case LogLevel.Error:
                        console.error(message)
                        break
                    case LogLevel.Warning:
                        console.warn(message)
                        break
                    case LogLevel.Info:
                        console.info(message)
                        break
                    case LogLevel.Verbose:
                        console.debug(message)
                        break
                }
            },
            logLevel: LogLevel.Warning
        }
    }
}

// Scopes for login
export const loginRequest = {
    scopes: ['User.Read', 'openid', 'profile', 'email']
}

// Scopes for API access (if you have a backend API)
export const apiRequest = {
    scopes: ['api://689d0170-0576-4563-8a24-a323625196ca/access_as_user']
}
