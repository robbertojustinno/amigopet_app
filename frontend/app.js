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
let isClientChatLoading = false;
let isWalkerChatLoading = false;
let chatPollingHandle = null;
let paymentPollingHandle = null;
let activePaymentRequestId = null;
let availableWalkers = [];
let availablePets = [];

const PRICE_BY_DURATION = { 15: 1, 30: 2, 45: 3, 60: 4 };

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

function startChatPolling() {
  stopChatPolling();
  chatPollingHandle = setInterval(async () => {
    if (activeChatRequestId) {
      await openChat(activeChatRequestId, byId("chatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", false, true);
    }
    if (activeWalkerChatRequestId) {
      await openChat(activeWalkerChatRequestId, byId("walkerChatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", true, true);
    }
  }, 3000);
}

function stopChatPolling() {
  if (chatPollingHandle) {
    clearInterval(chatPollingHandle);
    chatPollingHandle = null;
  }
}

function stopPaymentPolling() {
  if (paymentPollingHandle) {
    clearInterval(paymentPollingHandle);
    paymentPollingHandle = null;
  }
  activePaymentRequestId = null;
}

async function loadWalkers() {
  const select = byId("selected_walker_id");
  if (!select) return;

  try {
    const neighborhood = byId("walk_neighborhood")?.value?.trim() || "";
    const city = byId("walk_city")?.value?.trim() || "";

    const params = new URLSearchParams();
    if (neighborhood) params.set("neighborhood", neighborhood);
    if (city) params.set("city", city);

    const path = params.toString() ? `/walkers?${params.toString()}` : "/walkers";
    availableWalkers = await api(path);

    select.innerHTML = `<option value="">Selecione um passeador</option>`;
    availableWalkers.forEach((walker) => {
      const option = document.createElement("option");
      option.value = walker.id;
      option.textContent = `${walker.full_name} • ${walker.neighborhood || "-"} / ${walker.city || "-"}`;
      select.appendChild(option);
    });
  } catch (err) {
    console.log(err.message);
  }
}


async function loadPets() {
  const select = byId("selected_pet_id");
  if (!select || !currentUser?.id) return;

  try {
    availablePets = await api(`/pets/${currentUser.id}`);
    select.innerHTML = `<option value="">Selecione um pet</option>`;

    availablePets.forEach((pet) => {
      const option = document.createElement("option");
      option.value = pet.id;
      option.textContent = `${pet.name} • ${pet.breed || pet.size || "Sem raça informada"}`;
      select.appendChild(option);
    });
  } catch (err) {
    console.log(err.message);
  }
}

function renderSession(user) {
  currentUser = user || null;
  updateHeaderState();

  if (!user) {
    activeChatRequestId = null;
    activeWalkerChatRequestId = null;
    stopChatPolling();
    stopPaymentPolling();
    showScreen("welcomeScreen");
    return;
  }

  if (user.role === "admin") {
    activeChatRequestId = null;
    activeWalkerChatRequestId = null;
    stopChatPolling();
    stopPaymentPolling();
    if (byId("adminSessionInfo")) byId("adminSessionInfo").textContent = `${user.full_name || "Admin"} conectado`;
    showScreen("adminDashboard");
    loadAdminDashboard();
    return;
  }

  if (user.role === "walker") {
    activeChatRequestId = null;
    if (byId("walkerSessionInfo")) byId("walkerSessionInfo").textContent = `${user.full_name || "Passeador"} conectado`;
    showScreen("walkerDashboard");
    loadRequests();
    startChatPolling();
    return;
  }

  activeWalkerChatRequestId = null;
  if (byId("clientSessionInfo")) byId("clientSessionInfo").textContent = `${user.full_name || "Cliente"} conectado`;
  showScreen("clientDashboard");
  syncEstimatedPrice();
  tryAutoLocate();
  loadRequests();
  loadWalkers();
  loadPets();
  startChatPolling();
}

function logout() {
  localStorage.removeItem("session_user");
  localStorage.removeItem("access_token");
  currentUser = null;
  activeChatRequestId = null;
  activeWalkerChatRequestId = null;
  latestMercadoPagoLink = null;
  stopChatPolling();
  stopPaymentPolling();
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

  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
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
  const base = PRICE_BY_DURATION[duration] ?? 2;
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

  latestMercadoPagoLink = data.link_pagamento || null;

  const qrImage = data.qr_code_base64
    ? `<img src="data:image/png;base64,${data.qr_code_base64}" alt="QR Code Pix" style="max-width:260px; display:block; margin:14px auto;">`
    : "";

  const qrText = data.qr_code
    ? `<textarea readonly style="width:100%; min-height:110px;">${data.qr_code}</textarea>`
    : "";

  box.innerHTML = `
    <div class="payment-status-title">PIX gerado com sucesso</div>
    <div class="payment-status-subtitle">Valor: R$ ${Number(data.amount || 0).toFixed(2)}</div>
    <div class="payment-status-subtitle">Status: ${data.status || "pending"}</div>
    <div class="payment-status-subtitle">Solicitação: ${data.request_id ?? "não vinculada"}</div>
    <div class="payment-status-subtitle">Payment ID: ${data.payment_id ?? "-"}</div>
    ${qrImage}
    ${qrText}
    <div class="request-actions">
      ${latestMercadoPagoLink ? `<button type="button" class="card-action-btn" id="openPaymentInlineBtn">Abrir link do pagamento</button>` : ""}
      ${data.qr_code ? `<button type="button" class="secondary-btn" id="copyPixBtn">Copiar código PIX</button>` : ""}
    </div>
  `;

  byId("openPaymentInlineBtn")?.addEventListener("click", () => {
    if (latestMercadoPagoLink) window.open(latestMercadoPagoLink, "_blank");
  });

  byId("copyPixBtn")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(data.qr_code || "");
      alert("Código PIX copiado.");
    } catch {
      alert("Não foi possível copiar automaticamente.");
    }
  });
}

async function pollPaymentStatus(requestId) {
  try {
    const data = await api(`/pagamento/status/${requestId}`);
    if (data?.paid) {
      const box = byId("paymentStatusBox");
      if (box) {
        box.innerHTML = `
          <div class="payment-status-title">Pagamento confirmado</div>
          <div class="payment-status-subtitle">Solicitação #${requestId} foi paga com sucesso.</div>
        `;
      }
      stopPaymentPolling();
      await loadRequests();
    }
  } catch (err) {
    console.log(err.message);
  }
}

function startPaymentPolling(requestId) {
  stopPaymentPolling();
  activePaymentRequestId = Number(requestId);
  paymentPollingHandle = setInterval(() => {
    if (activePaymentRequestId) {
      pollPaymentStatus(activePaymentRequestId);
    }
  }, 5000);
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
    const paidTag = item.payment_status === "paid" ? `<span class="tag">PAGO</span>` : `<span class="tag">${item.payment_status}</span>`;
    const div = document.createElement("div");
    div.className = "request-card";
    div.innerHTML = `
      <div class="person-row">
        ${avatarHtml(requestPhotoForUser(item), requestTitleForUser(item))}
        ${item.pet_photo ? `<img class="avatar" src="${item.pet_photo}" alt="${item.pet_name || "Pet"}">` : ``}
        <div>
          <div class="request-card-title">${requestTitleForUser(item)}</div>
          <div class="request-meta">
            <span><span class="tag">${item.status}</span> ${paidTag}</span>
            <span>${item.pickup_address || "-"}</span>
            <span>${item.city || "-"} / ${item.neighborhood || "-"}</span>
            <span>Pet: ${item.pet_name || "Não informado"}</span>
            <span>${item.duration_minutes} min • R$ ${Number(item.price || 0).toFixed(2)}</span>
          </div>
        </div>
      </div>
      <div class="request-actions">
        ${item.payment_status !== "paid" ? `<button type="button" class="card-action-btn pay-btn" data-request-id="${item.id}" data-amount="${item.price || 1}">Gerar pagamento</button>` : ""}
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
        ${item.pet_photo ? `<img class="avatar" src="${item.pet_photo}" alt="${item.pet_name || "Pet"}">` : ``}
        <div>
          <div class="request-card-title">${item.client_name || `Cliente ${item.client_id}`}</div>
          <div class="request-meta">
            <span><span class="tag">${item.status}</span> <span class="tag">${item.payment_status}</span></span>
            <span>${item.pickup_address || "-"}</span>
            <span>Pet: ${item.pet_name || "Não informado"}</span>
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

async function openChat(requestId, label, isWalker, silent = false) {
  if (isWalker) {
    if (isWalkerChatLoading) return;
    isWalkerChatLoading = true;

    try {
      activeWalkerChatRequestId = Number(requestId);
      if (byId("walkerChatHeaderLabel")) byId("walkerChatHeaderLabel").textContent = `Conversa com ${label}`;
      const messages = await api(`/messages/${requestId}`);
      renderMessages("walkerChatList", messages);
    } catch (err) {
      if (!silent) alert(err.message);
    } finally {
      isWalkerChatLoading = false;
    }
  } else {
    if (isClientChatLoading) return;
    isClientChatLoading = true;

    try {
      activeChatRequestId = Number(requestId);
      if (byId("chatHeaderLabel")) byId("chatHeaderLabel").textContent = `Conversa com ${label}`;
      const messages = await api(`/messages/${requestId}`);
      renderMessages("chatList", messages);
    } catch (err) {
      if (!silent) alert(err.message);
    } finally {
      isClientChatLoading = false;
    }
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
    if (requestId) startPaymentPolling(requestId);
  } catch (err) {
    alert(err.message);
  }
}

async function handleLoginSubmit(e) {
  if (e) e.preventDefault();

  const email = byId("login_email")?.value.trim();
  const password = byId("login_password")?.value;

  if (!email || !password) {
    alert("Preencha e-mail e senha.");
    return false;
  }

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

      data = normalizeLoggedUser(data, currentAccessTab);

      if (currentAccessTab === "client" && data.role !== "client") {
        alert("Esse login não pertence a um cliente.");
        return false;
      }

      if (currentAccessTab === "walker" && data.role !== "walker") {
        alert("Esse login não pertence a um passeador.");
        return false;
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

  if (currentAccessTab === "admin") {
    alert("Cadastro de admin não está habilitado.");
    return false;
  }

  const forcedRole = currentAccessTab === "walker" ? "walker" : "client";

  if (forcedRole === "walker" && !byId("profile_photo")?.value.trim()) {
    alert("A foto do passeador é obrigatória.");
    return false;
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

  if (!currentUser?.id) {
    alert("Sessão do cliente não encontrada.");
    return false;
  }

  if (!byId("pet_photo")?.value.trim()) {
    alert("A foto do animal é obrigatória.");
    return false;
  }

  try {
    const payload = {
      owner_id: Number(currentUser.id),
      name: byId("pet_name")?.value || "",
      breed: byId("pet_breed")?.value || "",
      size: byId("pet_size")?.value || "medio",
      notes: byId("pet_notes")?.value || "",
      photo_url: byId("pet_photo")?.value.trim() || null,
      dog_count: Number(byId("dog_count")?.value || 1)
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
    await loadPets();
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleWalkSubmit(e) {
  if (e) e.preventDefault();

  if (!currentUser || currentUser.role !== "client") {
    alert("Sessão do cliente não encontrada.");
    return false;
  }

  const walkerId = Number(byId("selected_walker_id")?.value || 0);
  if (!walkerId) {
    alert("Selecione um passeador antes de criar a solicitação.");
    return false;
  }

  const petId = Number(byId("selected_pet_id")?.value || 0);
  if (!petId) {
    alert("Selecione um pet antes de criar a solicitação.");
    return false;
  }

  try {
    const dogCount = Number(byId("dog_count")?.value || 1);
    const notes = `${byId("walk_notes")?.value || ""} [DOG_COUNT:${dogCount}]`;

    const payload = {
      client_id: Number(currentUser.id),
      walker_id: walkerId,
      pet_id: petId,
      pickup_address: byId("pickup_address")?.value || byId("mapAddress")?.value || "",
      neighborhood: byId("walk_neighborhood")?.value || "",
      city: byId("walk_city")?.value || "",
      scheduled_at: byId("scheduled_at")?.value || null,
      duration_minutes: Number(byId("duration_minutes")?.value || 30),
      dog_count: dogCount,
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

  if (!activeChatRequestId) {
    alert("Abra o chat de uma solicitação primeiro.");
    return false;
  }

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
    await openChat(activeChatRequestId, byId("chatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", false);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

async function handleWalkerMessageSubmit(e) {
  if (e) e.preventDefault();

  if (!activeWalkerChatRequestId) {
    alert("Abra o chat de uma solicitação primeiro.");
    return false;
  }

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
    await openChat(activeWalkerChatRequestId, byId("walkerChatHeaderLabel")?.textContent.replace("Conversa com ", "") || "", true);
  } catch (err) {
    alert(err.message);
  }

  return false;
}

function attachMainEvents() {
  byId("logoutBtn")?.addEventListener("click", logout);

  byId("goToRegisterBtn")?.addEventListener("click", () => {
    if (currentAccessTab === "admin") {
      alert("Cadastro de admin não está habilitado nesta tela.");
      return;
    }
    showScreen("registerScreen");
  });

  byId("backToWelcomeBtn")?.addEventListener("click", () => showScreen("welcomeScreen"));
  byId("refreshAdminBtn")?.addEventListener("click", loadAdminDashboard);
  byId("loadRequestsBtn")?.addEventListener("click", loadRequests);
  byId("refreshWalkerBtn")?.addEventListener("click", loadRequests);
  byId("loadMapBtn")?.addEventListener("click", loadMap);
  byId("loadWalkersBtn")?.addEventListener("click", loadWalkers);
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
  byId("registerForm")?.addEventListener("submit", handleRegisterSubmit);
  byId("petForm")?.addEventListener("submit", handlePetSubmit);
  byId("walkForm")?.addEventListener("submit", handleWalkSubmit);
  byId("messageForm")?.addEventListener("submit", handleMessageSubmit);
  byId("walkerMessageForm")?.addEventListener("submit", handleWalkerMessageSubmit);

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