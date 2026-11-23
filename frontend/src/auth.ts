export type Session = {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  username: string;
  expiresAt: number;
};

const STORAGE_KEY = "elmstone.adjuster.session";

const region = import.meta.env.VITE_COGNITO_REGION as string | undefined;
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined;
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

export function authConfigured(): boolean {
  return Boolean(region && userPoolId && clientId);
}

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (!s.idToken || !s.expiresAt) return null;
    if (Date.now() >= s.expiresAt - 30_000) {
      clearSession();
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function saveSession(s: Session): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

export function clearSession(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

export async function login(username: string, password: string): Promise<Session> {
  if (!authConfigured() || !region || !clientId) {
    throw new Error("Cognito env vars missing (VITE_COGNITO_*)");
  }
  const res = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
    },
    body: JSON.stringify({
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: clientId,
      AuthParameters: {
        USERNAME: username,
        PASSWORD: password,
      },
    }),
  });
  const body = (await res.json()) as {
    message?: string;
    __type?: string;
    ChallengeName?: string;
    AuthenticationResult?: {
      IdToken: string;
      AccessToken: string;
      RefreshToken?: string;
      ExpiresIn: number;
    };
  };
  if (!res.ok) {
    throw new Error(body.message || body.__type || `Login failed (${res.status})`);
  }
  if (body.ChallengeName) {
    throw new Error(`Login challenge required: ${body.ChallengeName}`);
  }
  const result = body.AuthenticationResult;
  if (!result?.IdToken) {
    throw new Error("No tokens returned from Cognito");
  }
  const session: Session = {
    idToken: result.IdToken,
    accessToken: result.AccessToken,
    refreshToken: result.RefreshToken,
    username,
    expiresAt: Date.now() + result.ExpiresIn * 1000,
  };
  saveSession(session);
  return session;
}
