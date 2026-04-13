const API = window.API_BASE_URL || window.AMIGOPET_API_BASE || localStorage.getItem("AMIGOPET_API_BASE") || "/api";
const byId = (id) => document.getElementById(id);

let currentAccessTab = "client";
let currentUser = null;
let currentCoords = null;
let uploadedWalkerPhotoUrl = null;
let uploadedPetPhotoUrl = null;
let latestMercadoPagoLink = null;
let activeChatRequestId = null;
let activeWalkerChatRequestId = null;

const PRICE_BY_DURATION = { 15: 20, 30: 35, 45: 50, 60: 65 };

function normalizeLoggedUser(data, fallbackRole = null) {
  if (!data || typeof data !== "object") return data;
  const normalized = { ...data };

  if (normalized.user && typeof normalized.user === "object") {
    Object.assign(normalized, normalized.user);
  }

  if (!normalized.role && fallbackRole) normalized.role = fallbackRole;
  if (normalized.role === "administrator") normalized.role = "admin";
  if (normalized.role === "dog_walker") normalized.role = "walker";
  return normalized;
}

function showScreen(screenId) {
  document.querySelectorAll(".screen").forEach((screen) => screen.classList.remove("active"));
  byId(screenId)?.classList.add("active");
}

function setRoleChip(role) {
  document.querySelectorAll(".role-chip").forEach((btn) => btn.classList.toggle("active", btn.dataset.role === role));
}

function setAccessTab(tab) {
  currentAccessTab = tab;
  setRoleChip(tab);
  byId("goToRegisterBtn")?.classList.toggle("hidden", tab === "admin");
  byId("walkerPhotoArea")?.classList.toggle("hidden", tab !== "walker");
  if (byId("role")) byId("role").value = tab === "walker" ? "walker" : "client";

  if (tab === "admin") {
    if (byId("loginScreenTitle")) byId("loginScreenTitle").textContent = "Entrar como Admin";
    if (byId("loginScreenSubtitle")) byId("loginScreenSubtitle").textContent = "Acesse o painel administrativo";
    if (byId("registerScreenTitle")) byId("registerScreenTitle").textContent = "Cadastro de Admin";
    if (byId("registerScreenSubtitle")) byId("registerScreenSubtitle").textContent = "Cadastro desabilitado nesta tela";
  } else if (tab === "walker") {
    if (byId("loginScreenTitle")) byId("loginScreenTitle").textContent = "Entrar como Passeador";
    if (byId("loginScreenSubtitle")) byId("loginScreenSubtitle").textContent = "Acesse sua área de passeador";
    if (byId("registerScreenTitle")) byId("registerScreenTitle").textContent = "Criar conta de Passeador";
    if (byId("registerScreenSubtitle")) byId("registerScreenSubtitle").textContent = "Cadastre-se para receber solicitações";
  } else {
    if (byId("loginScreenTitle")) byId("loginScreenTitle").textContent = "Entrar como Cliente";
    if (byId("loginScreenSubtitle")) byId("loginScreenSubtitle").textContent = "Acesse sua área de cliente";
    if (byId("registerScreenTitle")) byId("registerScreenTitle").textContent = "Criar conta de Cliente";
    if (byId("registerScreenSubtitle")) byId("registerScreenSubtitle").textContent = "Cadastre-se para pedir passeios";
  }
}

function updateHeaderState() {
  byId("logoutBtn")?.classList.toggle("hidden", !currentUser);
}

function renderSession(user) {
  currentUser = user || null;
  updateHeaderState();

  if (!user) {
    showScreen("welcomeScreen");
    return;
  }

  if (user.role === "admin") {
    if (byId("adminSessionInfo")) byId("adminSessionInfo").textContent = `${user.full_name || "Admin"} conectado`;
    showScreen("adminDashboard");
    loadAdminDashboard();
    return;
  }

  if (user.role === "walker") {
    if (byId("walkerSessionInfo")) byId("walkerSessionInfo").textContent = `${user.full_name || "Passeador"} conectado`;
    showScreen("walkerDashboard");
    loadRequests();
    return;
  }

  if (byId("clientSessionInfo")) byId("clientSessionInfo").textContent = `${user.full_name || "Cliente"} conectado`;
  showScreen("clientDashboard");
  syncEstimatedPrice();
  tryAutoLocate();
  loadRequests();
}

function logout() {
  localStorage.removeItem("session_user");
  localStorage.removeItem("access_token");
  currentUser = null;
  activeChatRequestId = null;
  activeWalkerChatRequestId = null;
  latestMercadoPagoLink = null;
  renderSession(null);
  updatePaymentBoxDefault();
}

function base64Url(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const token = localStorage.getItem("access_token");
  if (token && !headers.Authorization) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API}${path}`, { ...options, headers });
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.detail || data.message || "Erro na requisição");
  }

  return data;
}

function buildMapUrl(address) {
  const q = encodeURIComponent(address);
  return `https://www.openstreetmap.org/export/embed.html?search=${q}&marker=1&query=${q}`;
}

function buildCoordsMapUrl(lat, lng) {
  const delta = 0.01;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${lng - delta}%2C${lat - delta}%2C${lng + delta}%2C${lat + delta}&layer=mapnik&marker=${lat}%2C${lng}`;
}

function applyDetectedLocation(lat, lng) {
  currentCoords = { lat, lng };
  const label = `Localização atual (${lat.toFixed(5)}, ${lng.toFixed(5)})`;

  ["address", "mapAddress", "pickup_address"].forEach((id) => {
    if (byId(id)) byId(id).value = label;
  });

  if (byId("mapFrame")) byId("mapFrame").src = buildCoordsMapUrl(lat, lng);
}

function loadMap() {
  const mapAddress = byId("mapAddress");
  const mapFrame = byId("mapFrame");
  if (!mapAddress || !mapFrame) return;

  const address = mapAddress.value.trim();

  if (currentCoords && (!address || address.startsWith("Localização atual"))) {
    mapFrame.src = buildCoordsMapUrl(currentCoords.lat, currentCoords.lng);
    return;
  }

  if (address) mapFrame.src = buildMapUrl(address);
}

function tryAutoLocate() {
  if (!navigator.geolocation) return loadMap();

  navigator.geolocation.getCurrentPosition(
    (position) => applyDetectedLocation(position.coords.latitude, position.coords.longitude),
    () => loadMap(),
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
  );
}

function syncEstimatedPrice() {
  const duration = Number(byId("duration_minutes")?.value || 30);
  const dogCount = Number(byId("dog_count")?.value || 1);
  const base = PRICE_BY_DURATION[duration] ?? 35;
  const multiplier = 1 + (dogCount - 1) * 0.6;
  const price = Math.round(base * multiplier);
  if (byId("price")) byId("price").value = price;
}

function setPhotoPreview(wrapId, imgId, src) {
  const wrap = byId(wrapId);
  const img = byId(imgId);
  if (!wrap || !img) return;

  if (!src) {
    wrap.classList.add("hidden");
    img.removeAttribute("src");
    return;
  }

  img.src = src;
  wrap.classList.remove("hidden");
}

function updatePaymentBoxDefault() {
  const box = byId("paymentStatusBox");
  if (!box) return;

  box.innerHTML = `
    <div class="payment-status-title">Nenhum pagamento gerado ainda.</div>
    <div class="payment-status-subtitle">Toque em “Gerar pagamento” no card da solicitação.</div>
  `;
}

function renderPaymentBox(data) {
  const box = byId("paymentStatusBox");
  if (!box) return;

  latestMercadoPagoLink = data.sandbox_link || data.link_pagamento || null;

  box.innerHTML = `
    <div class="payment-status-title">Pagamento gerado com sucesso</div>
    <div class="payment-status-subtitle">Valor: R$ ${Number(data.amount || 0).toFixed(2)}</div>
    <div class="payment-status-subtitle">Status: ${data.status || "created"}</div>
    <div class="payment-status-subtitle">Solicitação: ${data.request_id ?? "não vinculada"}</div>
    <div class="request-actions"><button type="button" class="card-action-btn" id="openPaymentInlineBtn">Abrir pagamento</button></div>
  `;

  byId("openPaymentInlineBtn")?.addEventListener("click", () => {
    if (latestMercadoPagoLink) window.open(latestMercadoPagoLink, "_blank");
  });
}

function avatarHtml(src, alt) {
  return src ? `<img class="avatar" src="${src}" alt="${alt}">` : `<div class="avatar"></div>`;
}

function renderAdminUsers(items) {
  const box = byId("adminUsersList");
  if (!box) return;

  box.innerHTML = !items?.length ? `<div class="item">Sem registros.</div>` : "";

  items?.forEach((item) => {
    const div = document.createElement("div");
    div.className = "request-card";
    div.innerHTML = `
      <div class="person-row">
        ${avatarHtml(item.profile_photo, item.full_name)}
        <div>
          <div class="request-card-title">${item.full_name}</div>
          <div class="request-meta"><span>${item.email}</span><span>${item.city || "-"} / ${item.neighborhood || "-"}</span><span class="tag">${item.role}</span></div>
        </div>
      </div>`;
    box.appendChild(div);
  });
}

function requestTitleForUser(item) {
  if (currentUser?.role === "walker") return item.client_name || `Cliente ${item.client_id}`;
  return item.walker_name || "Passeador a definir";
}

function requestPhotoForUser(item) {
  if (currentUser?.role === "walker") return item.client_photo;
  return item.walker_photo;
}

function renderClientRequests(items) {
  const box = byId("requestList");
  if (!box) return;

  box.innerHTML = !items?.length ? `<div class="item">Sem solicitações.</div>` : "";

  items?.forEach((item) => {
    const div = document.createElement("div");
    div.className = "request-card";
    div.innerHTML = `
      <div class="person-row">
        ${avatarHtml(requestPhotoForUser(item), requestTitleForUser(item))}
        <div>
          <div class="request-card-title">${requestTitleForUser(item)}</div>
          <div class="request-meta">
            <span><span class="tag">${item.status}</span> <span class="tag">${item.payment_status}</span></span>
            <span>${item.pickup_address || "-"}</span>
            <span>${item.city || "-"} / ${item.neighborhood || "-"}</span>
            <span>${item.duration_minutes} min • R$ ${Number(item.price || 0).toFixed(2)}</span>
          </div>
        </div>
      </div>
      <div class="request-actions">
        <button type="button" class="card-action-btn pay-btn" data-request-id="${item.id}" data-amount="${item.price || 35}">Gerar pagamento</button>
        <button type="button" class="ghost-btn open-chat-btn" data-request-id="${item.id}" data-label="${requestTitleForUser(item)}">Abrir chat</button>
      </div>`;
    box.appendChild(div);
  });

  box.querySelectorAll(".pay-btn").forEach((btn) => {
    btn.addEventListener("click", () => generateMercadoPagoPayment(btn.dataset.requestId, btn.dataset.amount));
  });

  box.querySelectorAll(".open-chat-btn").forEach((btn) => {
    btn.addEventListener("click", () => openChat(btn.dataset.requestId, btn.dataset.label, false));
  });
}

function renderWalkerRequests(items) {
  const box = byId("walkerRequestsInfo");
  if (!box) return;

  box.innerHTML = !items?.length ? `<div class="item">Sem solicitações para exibir.</div>` : "";

  items?.forEach((item) => {
    const div = document.createElement("div");
    div.className = "request-card";
    div.innerHTML = `
      <div class="person-row">
        ${avatarHtml(item.client_photo, item.client_name || `Cliente ${item.client_id}`)}
        <div>
          <div class="request-card-title">${item.client_name || `Cliente ${item.client_id}`}</div>
          <div class="request-meta">
            <span><span class="tag">${item.status}</span> <span class="tag">${item.payment_status}</span></span>
            <span>${item.pickup_address || "-"}</span>
            <span>${item.duration_minutes} min • R$ ${Number(item.price || 0).toFixed(2)}</span>
          </div>
        </div>
      </div>
      <div class="request-actions">
        <button type="button" class="card-action-btn walker-action-btn" data-action="accept" data-request-id="${item.id}">Aceitar</button>
        <button type="button" class="secondary-btn walker-action-btn" data-action="decline" data-request-id="${item.id}">Recusar</button>
        <button type="button" class="ghost-btn open-chat-btn" data-request-id="${item.id}" data-label="${item.client_name || `Cliente ${item.client_id}`}">Abrir chat</button>
      </div>`;
    box.appendChild(div);
  });

  box.querySelectorAll(".walker-action-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/walk-requests/${btn.dataset.requestId}/${btn.dataset.action}`, {
          method: "POST",
          body: JSON.stringify({ actor_id: currentUser.id })
        });
        loadRequests();
      } catch (err) {
        alert(err.message);
      }
    });
  });

  box.querySelectorAll(".open-chat-btn").forEach((btn) => {
    btn.addEventListener("click", () => openChat(btn.dataset.requestId, btn.dataset.label, true));
  });
}

function renderMessages(targetId, messages) {
  const box = byId(targetId);
  if (!box) return;

  box.innerHTML = !messages?.length ? `<div class="item">Sem mensagens.</div>` : "";

  messages?.forEach((item) => {
    const div = document.createElement("div");
    div.className = "chat-bubble";
    div.innerHTML = `<strong>${item.sender_name}${item.sender_role ? ` • ${item.sender_role === "walker" ? "Passeador" : "Cliente"}` : ""}</strong>${item.text}`;
    box.appendChild(div);
  });
}

async function openChat(requestId, label, isWalker) {
  if (isWalker) {
    activeWalkerChatRequestId = Number(requestId);
    if (byId("walkerChatHeaderLabel")) byId("walkerChatHeaderLabel").textContent = `Conversa com ${label}`;
    const messages = await api(`/messages/${requestId}`);
    renderMessages("walkerChatList", messages);
  } else {
    activeChatRequestId = Number(requestId);
    if (byId("chatHeaderLabel")) byId("chatHeaderLabel").textContent = `Conversa com ${label}`;
    const messages = await api(`/messages/${requestId}`);
    renderMessages("chatList", messages);
  }
}

async function loadAdminDashboard() {
  try {
    const data = await api("/admin/dashboard");
    if (byId("metricTotalUsers")) byId("metricTotalUsers").textContent = data.total_users ?? 0;
    if (byId("metricClients")) byId("metricClients").textContent = data.total_clients ?? 0;
    if (byId("metricWalkers")) byId("metricWalkers").textContent = data.total_walkers ?? 0;
    if (byId("metricRevenue")) byId("metricRevenue").textContent = `R$ ${Number(data.total_revenue || 0).toFixed(2)}`;
    if (byId("metricRequests")) byId("metricRequests").textContent = data.total_requests ?? 0;
    if (byId("metricCompleted")) byId("metricCompleted").textContent = data.total_completed ?? 0;
    if (byId("metricPaid")) byId("metricPaid").textContent = data.total_paid ?? 0;
    renderAdminUsers(await api("/admin/users"));
  } catch (err) {
    alert(err.message);
  }
}

async function loadRequests() {
  try {
    let path = "/walk-requests";
    if (currentUser?.id && currentUser.role !== "admin") {
      path += `?user_id=${encodeURIComponent(currentUser.id)}`;
    }
    const data = await api(path);
    renderClientRequests(currentUser?.role === "client" ? data : []);
    renderWalkerRequests(currentUser?.role === "walker" ? data : []);
  } catch (err) {
    console.log(err.message);
  }
}

async function generateMercadoPagoPayment(requestId = "", amount = "") {
  try {
    const query = new URLSearchParams();
    if (requestId) query.set("request_id", requestId);
    if (amount) query.set("amount", amount);
    const data = await api(`/pagamento?${query.toString()}`, { method: "GET" });
    renderPaymentBox(data);
  } catch (err) {
    alert(err.message);
  }
}

async function handleLoginSubmit(e) {
  if (e) e.preventDefault();

  const email = byId("login_email")?.value.trim();
  const password = byId("login_password")?.value;

  if (!email || !password) return alert("Preencha e-mail e senha.");

  try {
    let data;

    if (currentAccessTab === "admin") {
      data = await api("/admin/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      data = normalizeLoggedUser(data, "admin");
      data.role = "admin";
    } else {
      data = await api("/users/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });

      if (data?.access_token) {
        localStorage.setItem("access_token", data.access_token);
      }

      data = normalizeLoggedUser(data, currentAccessTab);

      if (currentAccessTab === "client" && data.role !== "client") {
        return alert("Esse login não pertence a um cliente.");
      }

      if (currentAccessTab === "walker" && data.role !== "walker") {
        return alert("Esse login não pertence a um passeador.");
      }
    }

    localStorage.setItem("session_user", JSON.stringify(data));
    renderSession(data);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleRegisterSubmit(e) {
  if (e) e.preventDefault();

  if (currentAccessTab === "admin") return alert("Cadastro de admin não está habilitado.");

  const forcedRole = currentAccessTab === "walker" ? "walker" : "client";

  if (forcedRole === "walker" && !byId("profile_photo")?.value.trim()) {
    return alert("A foto do passeador é obrigatória.");
  }

  try {
    const payload = {
      full_name: byId("full_name")?.value || "",
      email: byId("email")?.value || "",
      password: byId("password")?.value || "",
      role: forcedRole,
      neighborhood: byId("neighborhood")?.value || "",
      city: byId("city")?.value || "",
      address: byId("address")?.value || "",
      profile_photo: byId("profile_photo")?.value.trim() || null
    };

    let data = await api("/users/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    data = normalizeLoggedUser(data, forcedRole);

    alert(data?.id ? `Conta criada com ID ${data.id}` : "Conta criada com sucesso");

    byId("registerForm")?.reset();
    uploadedWalkerPhotoUrl = null;
    setPhotoPreview("photoPreviewWrap", "photoPreview", null);
    setAccessTab(forcedRole);
    localStorage.setItem("session_user", JSON.stringify(data));
    renderSession(data);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handlePetSubmit(e) {
  if (e) e.preventDefault();

  if (!currentUser?.id) return alert("Sessão do cliente não encontrada.");
  if (!byId("pet_photo")?.value.trim()) return alert("A foto do animal é obrigatória.");

  try {
    const payload = {
      owner_id: Number(currentUser.id),
      name: byId("pet_name")?.value || "",
      breed: byId("pet_breed")?.value || "",
      size: byId("pet_size")?.value || "medio",
      notes: `${byId("pet_notes")?.value || ""} [FOTO:${byId("pet_photo")?.value.trim()}]`
    };

    const data = await api("/pets", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    alert(`Pet salvo com ID ${data.id}`);
    byId("petForm")?.reset();
    uploadedPetPhotoUrl = null;
    setPhotoPreview("petPhotoPreviewWrap", "petPhotoPreview", null);
    if (byId("petPhotoUploadStatus")) byId("petPhotoUploadStatus").textContent = "Nenhuma foto selecionada.";
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleWalkSubmit(e) {
  if (e) e.preventDefault();

  if (!currentUser || currentUser.role !== "client") {
    return alert("Sessão do cliente não encontrada.");
  }

  try {
    const dogCount = Number(byId("dog_count")?.value || 1);
    const notes = `${byId("walk_notes")?.value || ""} [DOG_COUNT:${dogCount}]`;

    const payload = {
      client_id: Number(currentUser.id),
      walker_id: null,
      pet_id: null,
      pickup_address: byId("pickup_address")?.value || byId("mapAddress")?.value || "",
      neighborhood: byId("walk_neighborhood")?.value || "",
      city: byId("walk_city")?.value || "",
      scheduled_at: byId("scheduled_at")?.value || null,
      duration_minutes: Number(byId("duration_minutes")?.value || 30),
      price: Number(byId("price")?.value || 0),
      notes
    };

    const data = await api("/walk-requests", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    alert(`Solicitação criada com ID ${data.id}`);
    loadRequests();
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleMessageSubmit(e) {
  if (e) e.preventDefault();

  if (!activeChatRequestId) return alert("Abra o chat de uma solicitação primeiro.");

  try {
    await api("/messages", {
      method: "POST",
      body: JSON.stringify({
        walk_request_id: activeChatRequestId,
        sender_id: currentUser.id,
        text: byId("chat_text")?.value || ""
      })
    });

    if (byId("chat_text")) byId("chat_text").value = "";
    openChat(activeChatRequestId, byId("chatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", false);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleWalkerMessageSubmit(e) {
  if (e) e.preventDefault();

  if (!activeWalkerChatRequestId) return alert("Abra o chat de uma solicitação primeiro.");

  try {
    await api("/messages", {
      method: "POST",
      body: JSON.stringify({
        walk_request_id: activeWalkerChatRequestId,
        sender_id: currentUser.id,
        text: byId("walker_chat_text")?.value || ""
      })
    });

    if (byId("walker_chat_text")) byId("walker_chat_text").value = "";
    openChat(activeWalkerChatRequestId, byId("walkerChatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", true);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

function attachMainEvents() {
  byId("logoutBtn")?.addEventListener("click", logout);

  byId("goToRegisterBtn")?.addEventListener("click", () => {
    if (currentAccessTab === "admin") return alert("Cadastro de admin não está habilitado nesta tela.");
    showScreen("registerScreen");
  });

  byId("backToWelcomeBtn")?.addEventListener("click", () => showScreen("welcomeScreen"));
  byId("refreshAdminBtn")?.addEventListener("click", loadAdminDashboard);
  byId("loadRequestsBtn")?.addEventListener("click", loadRequests);
  byId("refreshWalkerBtn")?.addEventListener("click", loadRequests);
  byId("loadMapBtn")?.addEventListener("click", loadMap);
  byId("duration_minutes")?.addEventListener("change", syncEstimatedPrice);
  byId("dog_count")?.addEventListener("change", syncEstimatedPrice);

  document.querySelectorAll(".role-chip").forEach((btn) => {
    btn.addEventListener("click", () => setAccessTab(btn.dataset.role));
  });

  byId("choosePhotoBtn")?.addEventListener("click", () => byId("profile_photo_file")?.click());

  byId("clearPhotoBtn")?.addEventListener("click", () => {
    uploadedWalkerPhotoUrl = null;
    if (byId("profile_photo")) byId("profile_photo").value = "";
    if (byId("profile_photo_file")) byId("profile_photo_file").value = "";
    setPhotoPreview("photoPreviewWrap", "photoPreview", null);
    if (byId("photoUploadStatus")) byId("photoUploadStatus").textContent = "Nenhuma foto selecionada.";
  });

  byId("profile_photo_file")?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    uploadedWalkerPhotoUrl = await base64Url(file);
    if (byId("profile_photo")) byId("profile_photo").value = uploadedWalkerPhotoUrl;
    setPhotoPreview("photoPreviewWrap", "photoPreview", uploadedWalkerPhotoUrl);
    if (byId("photoUploadStatus")) byId("photoUploadStatus").textContent = `Foto carregada: ${file.name}`;
  });

  byId("choosePetPhotoBtn")?.addEventListener("click", () => byId("pet_photo_file")?.click());

  byId("clearPetPhotoBtn")?.addEventListener("click", () => {
    uploadedPetPhotoUrl = null;
    if (byId("pet_photo")) byId("pet_photo").value = "";
    if (byId("pet_photo_file")) byId("pet_photo_file").value = "";
    setPhotoPreview("petPhotoPreviewWrap", "petPhotoPreview", null);
    if (byId("petPhotoUploadStatus")) byId("petPhotoUploadStatus").textContent = "Nenhuma foto selecionada.";
  });

  byId("pet_photo_file")?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    uploadedPetPhotoUrl = await base64Url(file);
    if (byId("pet_photo")) byId("pet_photo").value = uploadedPetPhotoUrl;
    setPhotoPreview("petPhotoPreviewWrap", "petPhotoPreview", uploadedPetPhotoUrl);
    if (byId("petPhotoUploadStatus")) byId("petPhotoUploadStatus").textContent = `Foto carregada: ${file.name}`;
  });

  byId("loginForm")?.addEventListener("submit", handleLoginSubmit);
  byId("loginSubmitBtn")?.addEventListener("click", handleLoginSubmit);

  byId("registerForm")?.addEventListener("submit", handleRegisterSubmit);
  byId("registerSubmitBtn")?.addEventListener("click", handleRegisterSubmit);

  byId("petForm")?.addEventListener("submit", handlePetSubmit);
  byId("petSubmitBtn")?.addEventListener("click", handlePetSubmit);

  byId("walkForm")?.addEventListener("submit", handleWalkSubmit);
  byId("walkSubmitBtn")?.addEventListener("click", handleWalkSubmit);

  byId("messageForm")?.addEventListener("submit", handleMessageSubmit);
  byId("messageSubmitBtn")?.addEventListener("click", handleMessageSubmit);

  byId("walkerMessageForm")?.addEventListener("submit", handleWalkerMessageSubmit);
  byId("walkerMessageSubmitBtn")?.addEventListener("click", handleWalkerMessageSubmit);

  byId("expireBtn")?.addEventListener("click", async () => {
    try {
      await api("/maintenance/expire-invites", { method: "POST" });
      loadRequests();
    } catch (err) {
      alert(err.message);
    }
  });
}

window.addEventListener("load", () => {
  setAccessTab("client");
  updatePaymentBoxDefault();
  updateHeaderState();
  syncEstimatedPrice();
  attachMainEvents();
  tryAutoLocate();

  const session = localStorage.getItem("session_user");
  if (session) {
    try {
      renderSession(JSON.parse(session));
    } catch {
      renderSession(null);
    }
  } else {
    renderSession(null);
  }
});

setInterval(() => {
  if (activeChatRequestId) {
    openChat(
      activeChatRequestId,
      byId("chatHeaderLabel")?.textContent.replace("Conversa com ", "") || "",
      false
    );
  }

  if (activeWalkerChatRequestId) {
    openChat(
      activeWalkerChatRequestId,
      byId("walkerChatHeaderLabel")?.textContent.replace("Conversa com ", "") || "",
      true
    );
  }
}, 3000);