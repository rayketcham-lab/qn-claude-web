# Security Policy — QN Code Assistant

## Reporting Vulnerabilities

**Please do not open public GitHub issues for security vulnerabilities.**

### Option 1 — GitHub Security Advisories (preferred)

Use the private reporting channel built into GitHub:

1. Go to the repository on GitHub.
2. Click the **Security** tab.
3. Click **Report a vulnerability**.
4. Fill in the advisory form with reproduction steps, impact, and any suggested fixes.

GitHub will notify the maintainers privately and we will coordinate a fix and disclosure timeline with you.

### Option 2 — Email

Send details to the repository owner via the email address listed on the GitHub profile. Include:

- Description of the vulnerability and its impact
- Steps to reproduce (minimal proof of concept preferred)
- Affected versions
- Any suggested mitigations or fixes

### Response Timeline

| Milestone | Target |
|-----------|--------|
| Acknowledgement | 48 hours |
| Initial assessment | 5 business days |
| Fix or mitigation | 30 days for critical/high, 90 days for medium/low |
| Public disclosure | Coordinated with reporter |

We follow responsible disclosure. Please allow us the response window above before public disclosure.

---

## Security Model

### What the Application Protects

QN Code Assistant is a web frontend for the Claude Code CLI. The security controls in place are:

- **Authentication**: Single-user password login with bcrypt hashing. Rate limiting on the login endpoint (10 attempts per 5 minutes per IP). Session tokens are random and stored server-side.
- **File access control**: `validate_file_path()` enforces an allowlist of readable paths. The application directory itself (`/opt/claude-web/`) is excluded to prevent source, config, and session file leaks. Path traversal, null bytes, and symlink escapes are blocked.
- **Command injection**: PTY processes are spawned with argument lists (not shell strings). SSH commands are assembled with `shlex.quote()`. Remote host paths are validated.
- **Terminal output scoping**: Terminal I/O is scoped to the WebSocket session that owns the PTY — other connected clients cannot read another user's terminal output.
- **Rate limiting**: Login attempts are rate-limited per IP. Chat messages are capped at 1 MB.
- **Server hardening**: The `Server` response header is set to `QN Code Assistant` — no framework or Python version is exposed. All `request.json` accesses are guarded against null bodies.
- **SSH credential handling**: SSH key exchange uses environment variable injection for passwords (not command-line arguments). Private keys are never returned in API responses or logged.
- **Role-based config access**: Security-sensitive configuration keys require admin role.

### What the Application Does Not Protect

- **Multi-user isolation**: The application is designed for single-user or trusted-LAN use. There is no per-user data isolation beyond session scoping of terminal I/O. Do not expose this application to untrusted users on a shared host.
- **Secret key persistence**: The Flask secret key is stored in `config.json`. For high-security deployments inject it via the `SECRET_KEY` environment variable instead.
- **End-to-end encryption of terminal data**: WebSocket traffic should be encrypted at the transport layer (TLS). The application does not add encryption on top of the WebSocket stream.
- **Audit logging**: There is no tamper-evident audit log of commands run in terminal sessions.
- **CSP inline script restriction**: The Content Security Policy currently permits `unsafe-inline` for scripts. This is a known limitation tracked for a future release.

---

## Deployment Security Recommendations

### Network Exposure

- **Do not expose port 5001 directly to the internet.** The application is designed to run behind a reverse proxy (nginx, Caddy, Apache) that terminates TLS.
- Use a firewall to restrict access to the service port to trusted IP ranges or the loopback interface. Allow only the reverse proxy to reach port 5001.
- If remote access is required, prefer a VPN or SSH tunnel over direct internet exposure.

### Reverse Proxy (nginx example)

```nginx
server {
    listen 443 ssl;
    server_name your.host.example;

    ssl_certificate     /etc/ssl/certs/your.crt;
    ssl_certificate_key /etc/ssl/private/your.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

### File Permissions

```bash
# Application files — owned by the service user, not world-readable
sudo chown -R qnca:qnca /opt/claude-web
sudo chmod 750 /opt/claude-web
sudo chmod 640 /opt/claude-web/config.json

# config.json contains the password hash and secret key — restrict access
sudo chmod 600 /opt/claude-web/config.json
```

### Systemd Service Isolation

The included `qn-code-assistant.service` file enables several hardening directives. Verify the following are present and not overridden:

```ini
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/claude-web/chat_sessions /opt/claude-web/config.json
```

Do not run the service as `root`. Use a dedicated low-privilege service account.

### Secret Key

Move the Flask secret key out of `config.json` and into the environment:

```bash
# /etc/systemd/system/qn-code-assistant.service
[Service]
Environment=SECRET_KEY=<randomly-generated-64-char-hex>
```

Generate a value with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Password Strength

The application enforces a minimum password length of 8 characters. For internet-facing deployments use a strong random password (20+ characters) or consider adding HTTP Basic Auth at the reverse proxy layer as a second factor.

### Dependency Updates

Vendored Python packages in `vendor/` must be updated manually. The CI pipeline runs `pip-audit` against all vendored packages on every push. Review audit results in the `dependency-audit` CI job and update affected packages promptly when vulnerabilities are reported.

To update a vendored package:

1. Download the new wheel from PyPI.
2. Extract into `vendor/`, replacing the old package files and `.dist-info/` directory.
3. Run `bash build-installer.sh` to rebuild the installer with updated hashes.
4. Commit the updated vendor files and installer.

---

## Known Findings (Accepted Risk)

| ID | Package | Description | Risk | Status |
|----|---------|-------------|------|--------|
| CVE-2026-27205 | flask 3.1.2 | Missing `Vary: Cookie` header for some session access patterns — requires caching proxy in path | Low (no caching proxy in default deployment) | Pending vendor fix in 3.1.3 |
| CVE-2026-27199 | werkzeug 3.1.5 | `safe_join` Windows device name bypass — only exploitable on Windows | None (Linux deployment) | Accepted; will update on next routine vendor refresh |

These findings are surfaced by the `dependency-audit` CI job and will be resolved when fixed versions are vendored.
