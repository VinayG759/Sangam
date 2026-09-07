# Clerk Auth Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the authentication mechanism itself — a FastAPI dependency that verifies a Clerk-issued session token, one protected route that proves it end to end, and the frontend Clerk sign-in wiring that obtains and sends that token. This is deliberately just the plumbing: the actual policymaker-only features (saved scenarios, briefing exports, audit trail — F15) are later weeks and attach to this seam once it exists.

**Architecture:** Clerk hosts the login UI and issues signed JWTs; nothing about passwords or sessions is built here. The backend never talks to Clerk's API directly — it verifies tokens locally against Clerk's published JWKS (JSON Web Key Set), the standard stateless-JWT-verification pattern. The frontend wraps the app in `<ClerkProvider>`, and any authenticated request attaches the current session token as `Authorization: Bearer <token>`.

**Tech Stack:** Backend — `pyjwt[crypto]` for JWKS-based verification, FastAPI `Header`/`Depends`. Frontend — `@clerk/clerk-react`, React 19, Vite.

**Spec:** Sangam System Design Document §1 (F15), §10 (originally speced "Supabase Auth," superseded by this plan's Clerk decision), §17 "New capabilities" (`https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db`).

## Global Constraints

- $0 running cost: Clerk's free tier (10,000 monthly active users) covers this project's account count many times over — do not enable any paid Clerk add-on.
- Stage explicit file paths when committing (`git add <path>`), never `git add -A`.
- No `Co-Authored-By` trailer on commits.
- Before committing, run `git diff --cached --stat` and confirm it matches what you intended to stage.
- Backend routes use `AsyncSession`/`async def` (see `backend/app/routes/pack.py` for the house style) — `require_auth` must be an `async def` dependency to match.
- Frontend has no test runner installed (no vitest/jest, `npm run build` only type-checks via `tsc -b`) — this plan's frontend tasks are verified by a type-check plus an explicit manual browser step, matching how every other frontend feature in this repo has been verified so far. This is a real gap, not a shortcut taken here; if the project later adds a frontend test runner, these steps should get real tests retrofitted.

**Prerequisite (not a task in this plan — you must do this before Task 1):** Create a Clerk application at `https://dashboard.clerk.com` (a free account is sufficient). From its API Keys page you need three values: the **Publishable key** (`pk_...`), the **JWKS URL**, and the **Issuer** URL (both shown under "Advanced" / "JWT templates" on the same page). These become `VITE_CLERK_PUBLISHABLE_KEY` (frontend) and `CLERK_JWKS_URL` / `CLERK_ISSUER` (backend) below.

---

### Task 1: Backend — Clerk JWT verification

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Create: `backend/app/auth.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `async def require_auth(authorization: str | None = Header(default=None)) -> dict` — a FastAPI dependency other routes will `Depends()` on. The returned dict is the token's decoded claims; `claims["sub"]` is the Clerk user id. Also produces `verify_clerk_token(token: str) -> dict`, used directly by `require_auth` and by later features that need to verify a token outside the request-header path.

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt`, add this line after `slowapi>=0.1.9`:

```
pyjwt[crypto]>=2.8.0
```

Run: `cd backend && pip install -r requirements.txt`

- [ ] **Step 2: Add Clerk settings**

In `backend/app/config.py`, add these two lines inside the `Settings` class, after the `GEMINI_EMBEDDING_DIM: int = 768` line:

```python
    # Clerk authentication (Phase 2 -- see docs/superpowers/plans/2026-08-25-clerk-auth-foundation.md).
    # JWKS_URL and ISSUER both come from the Clerk dashboard's API Keys ->
    # Advanced page for your application.
    CLERK_JWKS_URL: Optional[str] = None
    CLERK_ISSUER: Optional[str] = None
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_auth.py`:

```python
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
import jwt as pyjwt

import app.auth as auth_module
from app.auth import verify_clerk_token, require_auth


def test_verify_clerk_token_valid_token_returns_claims(monkeypatch):
    fake_signing_key = MagicMock()
    fake_signing_key.key = "fake-public-key"
    fake_client = MagicMock()
    fake_client.get_signing_key_from_jwt.return_value = fake_signing_key
    monkeypatch.setattr(auth_module, "_get_jwks_client", lambda: fake_client)
    monkeypatch.setattr(auth_module.jwt, "decode", lambda *a, **kw: {"sub": "user_123"})

    claims = verify_clerk_token("sometoken")

    assert claims == {"sub": "user_123"}
    fake_client.get_signing_key_from_jwt.assert_called_once_with("sometoken")


def test_verify_clerk_token_invalid_signature_raises_401(monkeypatch):
    fake_client = MagicMock()
    fake_client.get_signing_key_from_jwt.return_value = MagicMock(key="fake-key")
    monkeypatch.setattr(auth_module, "_get_jwks_client", lambda: fake_client)

    def raise_invalid(*a, **kw):
        raise pyjwt.InvalidSignatureError("bad signature")
    monkeypatch.setattr(auth_module.jwt, "decode", raise_invalid)

    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token("badtoken")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(authorization=None)
    assert exc_info.value.status_code == 401
    assert "Missing or malformed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_auth_malformed_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(authorization="NotBearer xyz")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_valid_bearer_delegates_to_verify(monkeypatch):
    mock_verify = MagicMock(return_value={"sub": "user_1"})
    monkeypatch.setattr(auth_module, "verify_clerk_token", mock_verify)

    claims = await require_auth(authorization="Bearer sometoken")

    assert claims == {"sub": "user_1"}
    mock_verify.assert_called_once_with("sometoken")
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'` (the module doesn't exist yet).

- [ ] **Step 5: Implement `app/auth.py`**

Create `backend/app/auth.py`:

```python
import jwt
from fastapi import Header, HTTPException
from app.config import settings

_jwks_client: "jwt.PyJWKClient | None" = None


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        if not settings.CLERK_JWKS_URL:
            raise HTTPException(status_code=500, detail="CLERK_JWKS_URL is not configured")
        _jwks_client = jwt.PyJWKClient(settings.CLERK_JWKS_URL)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    """
    Verifies a Clerk-issued session JWT against Clerk's published JWKS and
    returns its claims. Raises HTTPException(401) for any invalid, expired,
    or wrong-issuer token -- never returns a partially-trusted result.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER,
            options={"verify_aud": False},
        )
        return claims
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid session token: {e}")


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """
    FastAPI dependency: gates a route behind a valid Clerk session token.
    Expects `Authorization: Bearer <token>`. Returns the decoded claims dict
    (claims["sub"] is the Clerk user id) so the route can use it directly.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[len("Bearer "):]
    return verify_clerk_token(token)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/config.py backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat: verify Clerk session tokens for backend auth"
```

---

### Task 2: Backend — protected proof route

**Files:**
- Create: `backend/app/routes/admin.py`
- Modify: `backend/app/routes/__init__.py`
- Test: `backend/tests/test_routes.py`

**Interfaces:**
- Consumes: `require_auth` from Task 1 (`backend/app/auth.py`).
- Produces: `GET /api/v1/admin/whoami` — no other task in this plan depends on this route's shape, but it's the concrete thing Task 4 (frontend) calls to prove the whole loop works.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_routes.py`. After the imports at the top of the file (near `from fastapi.testclient import TestClient`), add:

```python
from app.auth import require_auth
```

Then, near the end of the file (after the last existing test class), add:

```python
# ── Admin (auth) ─────────────────────────────────────────────────────────────

class TestAdminWhoamiRoute:

    def test_whoami_without_auth_returns_401(self, client, mock_db_session):
        response = client.get("/api/v1/admin/whoami")
        assert response.status_code == 401

    def test_whoami_with_valid_auth_returns_user_id(self, client, mock_db_session):
        async def override_require_auth():
            return {"sub": "user_abc123"}
        app.dependency_overrides[require_auth] = override_require_auth

        response = client.get("/api/v1/admin/whoami", headers={"Authorization": "Bearer faketoken"})

        assert response.status_code == 200
        assert response.json() == {"user_id": "user_abc123"}

        del app.dependency_overrides[require_auth]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_routes.py::TestAdminWhoamiRoute -v`
Expected: FAIL — both tests get a 404, since `/api/v1/admin/whoami` doesn't exist yet.

- [ ] **Step 3: Implement the route**

Create `backend/app/routes/admin.py`:

```python
"""
Authenticated-only routes. Every route here requires a valid Clerk session
token via the require_auth dependency -- this module is the seam later
Phase 2 features (saved scenarios, briefing exports, audit trail) attach to.
"""

from fastapi import APIRouter, Depends
from app.auth import require_auth

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/whoami")
async def whoami(claims: dict = Depends(require_auth)):
    """
    Proves the auth wiring end to end: a valid Clerk session token in, the
    Clerk user id back out. No route below this file exists yet that a real
    policymaker feature depends on -- this one exists to be tested.
    """
    return {"user_id": claims.get("sub")}
```

In `backend/app/routes/__init__.py`, add the import after `from app.routes.webhooks import router as webhooks_router`:

```python
from app.routes.admin import router as admin_router
```

And add `admin_router` to the `all_routers` list, after `webhooks_router`:

```python
all_routers = [
    overview_router,
    priorities_router,
    regions_router,
    reports_router,
    expenditures_router,
    clusters_router,
    pack_router,
    webhooks_router,
    admin_router,
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_routes.py::TestAdminWhoamiRoute -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes, including every pre-existing test in `test_routes.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/admin.py backend/app/routes/__init__.py backend/tests/test_routes.py
git commit -m "feat: add auth-protected whoami route"
```

---

### Task 3: Frontend — ClerkProvider wiring

**Files:**
- Modify: `frontend/package.json` (via `npm install`, not a hand edit)
- Modify: `frontend/src/main.tsx`
- Create: `frontend/.env.example`

**Interfaces:**
- Produces: the whole app tree rendered inside `<ClerkProvider>`, which is what makes `@clerk/clerk-react`'s hooks (`useAuth`, `useUser`) and components (`SignedIn`, `SignedOut`, `SignInButton`, `UserButton`) usable anywhere in the tree — Task 4 consumes this directly.

- [ ] **Step 1: Install the Clerk SDK**

Run: `cd frontend && npm install @clerk/clerk-react`

- [ ] **Step 2: Add the frontend env template**

Create `frontend/.env.example`:

```
# ─────────────────────────────────────────────────────────────────────────────
# Sangam Frontend — Environment Variables
# Copy to .env.local and fill in the values:
#   cp .env.example .env.local
# ─────────────────────────────────────────────────────────────────────────────

# Backend API base URL. Leave blank for same-origin (local dev proxy).
VITE_API_URL=

# Clerk publishable key (starts with pk_test_ or pk_live_).
# From the Clerk dashboard: https://dashboard.clerk.com -> your app -> API Keys
VITE_CLERK_PUBLISHABLE_KEY=
```

Then run `cp frontend/.env.example frontend/.env.local` and fill in `VITE_CLERK_PUBLISHABLE_KEY` with the real publishable key from the Clerk dashboard prerequisite step at the top of this plan.

- [ ] **Step 3: Wrap the app in `ClerkProvider`**

Open `frontend/src/main.tsx`. Replace its full contents with:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import './index.css'
import App from './App.tsx'
import CitizenPortal from './pages/CitizenPortal.tsx'

const path = window.location.pathname;
const CLERK_PUBLISHABLE_KEY = ((import.meta as unknown) as Record<string, unknown> & { env?: Record<string, string> }).env?.VITE_CLERK_PUBLISHABLE_KEY ?? '';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
      {path === '/report' ? <CitizenPortal /> : <App />}
    </ClerkProvider>
  </StrictMode>,
)
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run build`
Expected: builds cleanly with no TypeScript errors.

- [ ] **Step 5: Manual verification**

Run: `cd frontend && npm run dev`, open the printed local URL in a browser, confirm the dashboard still loads exactly as before (no visible change yet — this task only wires the provider, Task 4 adds visible UI). Check the browser console for a Clerk error about a missing/invalid publishable key; if `VITE_CLERK_PUBLISHABLE_KEY` isn't set yet, `ClerkProvider` will throw there — that's expected until the Clerk dashboard prerequisite is complete.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/.env.example frontend/src/main.tsx
git commit -m "feat: wrap app in ClerkProvider"
```

---

### Task 4: Frontend — sign-in UI and end-to-end proof

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/AuthProbe.tsx`
- Modify: `frontend/src/components/Header.tsx`

**Interfaces:**
- Consumes: `ClerkProvider` context from Task 3, `GET /api/v1/admin/whoami` from Task 2.
- Produces: no interface other tasks in this plan depend on — this is the final, visible proof that the whole chain (Clerk sign-in → session token → backend verification → claims) works.

- [ ] **Step 1: Add the API call**

Open `frontend/src/api.ts`. Add this interface near the other interfaces (after `export interface PackInfo { ... }`):

```ts
export interface AdminWhoami {
  user_id: string;
}
```

Add this method inside the `export const api = { ... }` object, after the `checkStatus` method:

```ts
  adminWhoami: (token: string) =>
    fetch(`${BASE}/api/v1/admin/whoami`, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => {
        if (!res.ok) throw new Error(`GET /api/v1/admin/whoami failed: ${res.status}`);
        return res.json() as Promise<AdminWhoami>;
      }),
```

- [ ] **Step 2: Create the AuthProbe component**

Create `frontend/src/components/AuthProbe.tsx`:

```tsx
import { useState } from 'react'
import { SignedIn, SignedOut, SignInButton, UserButton, useAuth } from '@clerk/clerk-react'
import { api } from '@/api'

export default function AuthProbe() {
  const { getToken } = useAuth()
  const [status, setStatus] = useState<'idle' | 'checking' | 'ok' | 'error'>('idle')
  const [userId, setUserId] = useState<string | null>(null)

  async function checkAuth() {
    setStatus('checking')
    try {
      const token = await getToken()
      if (!token) throw new Error('No session token')
      const result = await api.adminWhoami(token)
      setUserId(result.user_id)
      setStatus('ok')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <SignedOut>
        <SignInButton mode="modal">
          <button className="btn btn-ghost" style={{ fontSize: 12 }}>Sign in</button>
        </SignInButton>
      </SignedOut>
      <SignedIn>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={checkAuth}>
          {status === 'checking' ? 'Checking…' : status === 'ok' ? `✓ ${userId}` : status === 'error' ? 'Auth check failed' : 'Verify session'}
        </button>
        <UserButton />
      </SignedIn>
    </div>
  )
}
```

- [ ] **Step 3: Wire it into the Header**

Open `frontend/src/components/Header.tsx`. Add this import after `import { LayoutGridIcon, ListRankedIcon, SlidersIcon, FileTextIcon } from '@/components/icons'`:

```tsx
import AuthProbe from '@/components/AuthProbe'
```

Find the closing of the "Pack info pill" block:

```tsx
        {pack && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 12px', borderRadius: 999,
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            fontSize: 11, color: 'var(--text-muted)',
            flexShrink: 0,
          }}>
            {pack.country_code} · {pack.sectors.length} sectors
          </div>
        )}
      </div>
    </header>
  )
}
```

Replace it with (adding `<AuthProbe />` right before the closing `</div>` of the header row):

```tsx
        {pack && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 12px', borderRadius: 999,
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            fontSize: 11, color: 'var(--text-muted)',
            flexShrink: 0,
          }}>
            {pack.country_code} · {pack.sectors.length} sectors
          </div>
        )}

        <AuthProbe />
      </div>
    </header>
  )
}
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run build`
Expected: builds cleanly with no TypeScript errors.

- [ ] **Step 5: Manual verification**

Run: `cd frontend && npm run dev`, open the dashboard in a browser. Confirm a "Sign in" button appears in the header. Click it, complete a real sign-in through Clerk's modal (create a test account if you don't have one yet — Clerk's own UI handles this). Once signed in, confirm the header now shows a "Verify session" button and a Clerk user avatar. Click "Verify session" and confirm it changes to `✓ <your Clerk user id>` — that's the full loop (frontend token → backend JWKS verification → claims) working end to end. If it shows "Auth check failed" instead, open the browser's network tab, find the failed `/api/v1/admin/whoami` request, and check the backend logs for the actual verification error (most likely cause: `CLERK_JWKS_URL`/`CLERK_ISSUER` not set in the backend's environment, or set to the wrong Clerk application).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/AuthProbe.tsx frontend/src/components/Header.tsx
git commit -m "feat: add Clerk sign-in UI and end-to-end auth verification"
```
