/** Verify the caller with Supabase Auth before accessing privileged AWS/DB clients. */
export class AuthError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

export async function requireUser(event: { headers?: Record<string, string> }) {
  const headers = Object.fromEntries(Object.entries(event.headers ?? {}).map(([key, value]) => [key.toLowerCase(), value]));
  const bearer = headers.authorization ?? '';
  if (!/^Bearer \S+$/.test(bearer) || bearer.length > 8192) {
    throw new AuthError(401, 'Sign in to run or manage tests.');
  }
  let response: Response;
  try {
    response = await fetch(`${process.env.SUPABASE_URL}/auth/v1/user`, {
      headers: { Authorization: bearer, apikey: process.env.SUPABASE_ANON_KEY! },
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new AuthError(503, 'Authentication is temporarily unavailable. Please try again.');
  }
  if (response.status === 401 || response.status === 403) {
    throw new AuthError(401, 'Your session has expired. Sign in again.');
  }
  if (!response.ok) throw new AuthError(503, 'Authentication is temporarily unavailable. Please try again.');
  let user: { id?: unknown; email?: unknown; is_anonymous?: unknown; identities?: unknown } | null;
  try {
    user = await response.json() as typeof user;
  } catch {
    throw new AuthError(503, 'Authentication is temporarily unavailable. Please try again.');
  }
  if (!user || typeof user.id !== 'string' || !user.id || user.is_anonymous ||
      !Array.isArray(user.identities) || !user.identities.some((identity) => identity?.provider === 'google')) {
    throw new AuthError(403, 'Google authentication is required.');
  }
  return { id: user.id, email: typeof user.email === 'string' ? user.email : undefined };
}
