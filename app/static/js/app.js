/**
 * Shared frontend helpers for JWT authentication, API calls, and UI formatting.
 */

function getToken() {
  return localStorage.getItem("access_token");
}

function setToken(token) {
  localStorage.setItem("access_token", token);
}

function logout() {
  localStorage.removeItem("access_token");
  window.location.href = "/login";
}

async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && window.location.pathname !== "/login") {
    logout();
    throw new Error("Session expired. Redirecting to login.");
  }

  if (response.status === 204) {
    return null;
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.detail || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

function showAlert(containerId, message, type = "error") {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = message;
  el.classList.remove("hidden");
}

function hideAlert(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.classList.add("hidden");
}

function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

/**
 * Verify login via GET /api/me, populate navbar info, and toggle role-based links.
 * Note: actual security is enforced on the backend via `require_role`.
 */
async function requireAuthPage() {
  if (!getToken()) {
    window.location.href = "/login";
    return null;
  }

  try {
    const user = await apiFetch("/api/me");
    const userLabel = document.getElementById("nav-user-label");
    if (userLabel) {
      userLabel.innerHTML = `${user.name} <span class="badge badge-role">${user.role}</span>`;
    }

    // Only employees can submit leave requests
    if (user.role === "employee") {
      document.getElementById("nav-request")?.classList.remove("hidden");
    }
    if (user.role === "manager") {
      document.getElementById("nav-approvals")?.classList.remove("hidden");
    }
    if (user.role === "admin") {
      document.getElementById("nav-admin")?.classList.remove("hidden");
    }

    // Highlight active nav link
    document.querySelectorAll(".nav-links a").forEach((link) => {
      if (link.getAttribute("href") === window.location.pathname) {
        link.classList.add("active");
      }
    });

    return user;
  } catch (err) {
    logout();
    return null;
  }
}