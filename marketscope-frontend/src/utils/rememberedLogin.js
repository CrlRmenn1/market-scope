// "Remember my email" on the login form. Only the email is kept; passwords are
// left to the browser's password manager.
const REMEMBERED_LOGIN_KEY = 'marketscope_login_remembered';

const readStoredLogin = () => {
  try {
    return JSON.parse(localStorage.getItem(REMEMBERED_LOGIN_KEY));
  } catch {
    return null;
  }
};

export const readRememberedEmail = () => {
  const email = readStoredLogin()?.email;
  return typeof email === 'string' ? email : '';
};

export const saveRememberedEmail = (email) => {
  try {
    localStorage.setItem(REMEMBERED_LOGIN_KEY, JSON.stringify({ email }));
  } catch {
    // Storage unavailable: the email just won't be remembered.
  }
};

export const clearRememberedEmail = () => {
  try {
    localStorage.removeItem(REMEMBERED_LOGIN_KEY);
  } catch {
    // Storage unavailable: nothing to clear.
  }
};

// Older versions also stored the password here as plain text. Runs on every app
// load, including for people who are already logged in and never see the form.
export const removeStoredPassword = () => {
  const stored = readStoredLogin();
  if (stored === null || typeof stored !== 'object') {
    clearRememberedEmail();
    return;
  }
  if ('password' in stored) saveRememberedEmail(readRememberedEmail());
};
