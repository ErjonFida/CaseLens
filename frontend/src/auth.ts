const TOKEN_KEY = 'legal_assistant_token';

export const getStoredToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const setStoredToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

export const removeStoredToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};

export const fetchWithAuth = async (url: string, options: RequestInit = {}): Promise<Response> => {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(url, { ...options, headers });
  // A token the server stopped accepting (they expire) ends the session
  // wherever that is noticed, not only on the dashboard's first load.
  if (res.status === 401 && token) {
    removeStoredToken();
    window.location.assign('/login');
  }
  return res;
};
