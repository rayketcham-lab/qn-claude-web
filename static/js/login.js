/* QN Code Assistant - Login Page Script */

(async function() {
    const status = await fetch('/api/auth/status').then(r => r.json());
    const isSetup = status.needs_setup;

    if (isSetup) {
        document.getElementById('login-subtitle').textContent = 'Create your account to get started';
        document.getElementById('confirm-field').style.display = 'block';
        document.getElementById('login-btn').textContent = 'Create Account';
        document.getElementById('password').autocomplete = 'new-password';
    }

    if (status.authenticated) {
        window.location.href = '/';
        return;
    }

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('login-error');
        errorEl.classList.remove('visible');

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        if (isSetup) {
            const confirm = document.getElementById('password-confirm').value;
            if (password !== confirm) {
                errorEl.textContent = 'Passwords do not match';
                errorEl.classList.add('visible');
                return;
            }
            // Setup new account
            try {
                const res = await fetch('/api/auth/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();
                if (data.success) {
                    window.location.href = '/';
                } else {
                    errorEl.textContent = data.error || 'Setup failed';
                    errorEl.classList.add('visible');
                }
            } catch (err) {
                errorEl.textContent = 'Connection error';
                errorEl.classList.add('visible');
            }
        } else {
            // Login
            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();
                if (data.success) {
                    window.location.href = '/';
                } else {
                    errorEl.textContent = data.error || 'Invalid credentials';
                    errorEl.classList.add('visible');
                }
            } catch (err) {
                errorEl.textContent = 'Connection error';
                errorEl.classList.add('visible');
            }
        }
    });
})();
