(() => {
  const form = document.getElementById("loginForm");
  const err = document.getElementById("loginError");
  const btn = document.getElementById("loginBtn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const username = form.username.value.trim();
    const password = form.password.value;
    if (!username || !password) {
      err.textContent = "Enter both username and password.";
      err.hidden = false;
      return;
    }
    btn.disabled = true;
    try {
      await SHMS.api("/api/login", { method: "POST", body: { username, password } });
      const next = form.dataset.next;
      location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
      btn.disabled = false;
    }
  });
})();
