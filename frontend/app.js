const API = "/api";

const byId = (id) => document.getElementById(id);

let paymentId = null;
let paymentCheckInterval = null;
let currentOrderId = null;
let currentOrderStatus = null;
let currentUser = null;

async function api(path, options = {}) {
  const config = {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  };

  const response = await fetch(`${API}${path}`, config);

  let data = null;
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    const text = await response.text();
    data = text ? { detail: text } : null;
  }

  if (!response.ok) {
    const message =
      data?.detail ||
      data?.message ||
      `Erro HTTP ${response.status}`;

    throw new Error(
      typeof message === "string" ? message : JSON.stringify(message)
    );
  }

  return data;
}

function setActiveTab(tab) {
  const loginTab = byId("loginTab");
  const registerTab = byId("registerTab");
  const tabLoginBtn = byId("tabLoginBtn");
  const tabRegisterBtn = byId("tabRegisterBtn");

  if (tab === "register") {
    loginTab?.classList.add("hidden");
    registerTab?.classList.remove("hidden");
    tabLoginBtn?.classList.remove("active");
    tabRegisterBtn?.classList.add("active");
  } else {
    registerTab?.classList.add("hidden");
    loginTab?.classList.remove("hidden");
    tabRegisterBtn?.classList.remove("active");
    tabLoginBtn?.classList.add("active");
  }
}

function showScreen(screenId) {
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.remove("active");
  });

  byId(screenId)?.classList.add("active");

  const onDashboard = screenId === "dashboardScreen";
  byId("logoutBtn")?.classList.toggle("hidden", !onDashboard);
  byId("showWelcomeBtn")?.classList.toggle("hidden", !onDashboard);
}

function updateSessionInfo() {
  const box = byId("sessionInfo");
  if (!box) return;

  if (!currentUser) {
    box.textContent = "Nenhuma sessão ativa";
    return;
  }

  box.textContent = `Sessão ativa: ${currentUser.email || "sem e-mail"} • ${currentUser.role || "user"}`;
}

function setStatusBox(id, message, variant = "") {
  const el = byId(id);
  if (!el) return;

  el.className = "status-box";
  if (variant) el.classList.add(variant);
  el.textContent = message;
}

function appendLog(message, variant = "") {
  setStatusBox("appLog", message, variant);
}

function renderOrderSummary() {
  const lines = [];

  if (!currentUser) {
    lines.push("Usuário: não autenticado");
  } else {
    lines.push(`Usuário: ${currentUser.email || "sem e-mail"}`);
    lines.push(`Perfil: ${currentUser.role || "user"}`);
  }

  lines.push(`Pedido atual: ${currentOrderId ?? "nenhum"}`);
  lines.push(`Status do pedido: ${currentOrderStatus ?? "nenhum"}`);
  lines.push(`Payment ID: ${paymentId ?? "nenhum"}`);

  setStatusBox("orderSummary", lines.join("\n"));
}

function stopPaymentMonitoring() {
  if (paymentCheckInterval) {
    clearInterval(paymentCheckInterval);
    paymentCheckInterval = null;
  }
}

function renderPixQrCode(base64, pixCode = "") {
  const qrSection = byId("qrSection");
  const img = byId("pixPreview");
  const codeBox = byId("pixCodeText");

  if (!qrSection || !img || !codeBox) return;

  if (base64) {
    img.src = `data:image/png;base64,${base64}`;
    qrSection.classList.remove("hidden");
  }

  if (pixCode) {
    codeBox.textContent = pixCode;
    codeBox.classList.remove("hidden");
  } else {
    codeBox.textContent = "";
    codeBox.classList.add("hidden");
  }
}

function clearPixDisplay() {
  const qrSection = byId("qrSection");
  const img = byId("pixPreview");
  const codeBox = byId("pixCodeText");

  if (img) img.removeAttribute("src");
  if (codeBox) {
    codeBox.textContent = "";
    codeBox.classList.add("hidden");
  }
  qrSection?.classList.add("hidden");
}

function getLoginPayload() {
  return {
    email: byId("login_email")?.value?.trim() || "",
    password: byId("login_password")?.value || ""
  };
}

function getRegisterPayload() {
  return {
    full_name: byId("full_name")?.value?.trim() || "",
    email: byId("email")?.value?.trim() || "",
    password: byId("password")?.value || "",
    role: byId("role")?.value || "client",
    neighborhood: "",
    city: "",
    address: "",
    photo: ""
  };
}

async function handleLogin(event) {
  event.preventDefault();

  try {
    const payload = getLoginPayload();

    const data = await api("/users/login", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    currentUser = data;
    localStorage.setItem("amigopet_user", JSON.stringify(data));

    updateSessionInfo();
    renderOrderSummary();
    showScreen("dashboardScreen");
    setStatusBox("paymentStatusBox", "Login realizado com sucesso. Sistema pronto para criar pedido e gerar PIX.", "success");
    appendLog("Login realizado com sucesso.", "success");
    await carregarHistoricoPedidos();
  } catch (error) {
    appendLog(`Erro no login: ${error.message}`, "error");
    alert(`Erro no login: ${error.message}`);
  }
}

async function handleRegister(event) {
  event.preventDefault();

  try {
    const payload = getRegisterPayload();

    const data = await api("/users/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    appendLog(`Conta criada com sucesso! ID: ${data.id ?? "sem retorno de ID"}`, "success");
    alert(`Conta criada com sucesso! ID: ${data.id ?? "sem retorno de ID"}`);

    byId("registerForm")?.reset();
    if (byId("role")) byId("role").value = "client";
    setActiveTab("login");
  } catch (error) {
    appendLog(`Erro ao criar conta: ${error.message}`, "error");
    alert(`Erro ao criar conta: ${error.message}`);
  }
}

async function consultarStatusAgora() {
  if (!paymentId) {
    appendLog("Nenhum pagamento ativo para consultar.", "warning");
    return;
  }

  try {
    const data = await api(`/payment/status/${paymentId}`, { method: "GET" });

    if (data.approved) {
      currentOrderStatus = "paid";
      renderOrderSummary();
      setStatusBox("paymentStatusBox", `Pagamento confirmado.\nStatus: ${data.status}\nPedido liberado.`, "success");
      appendLog("Pagamento confirmado manualmente.", "success");
    } else {
      setStatusBox("paymentStatusBox", `Pagamento ainda não aprovado.\nStatus atual: ${data.status || "desconhecido"}`, "warning");
      appendLog(`Consulta manual de status: ${data.status || "desconhecido"}`, "warning");
    }

    await carregarHistoricoPedidos();
  } catch (error) {
    appendLog(`Erro ao consultar status: ${error.message}`, "error");
    alert(`Erro ao consultar status: ${error.message}`);
  }
}

function monitorarPagamento() {
  stopPaymentMonitoring();

  paymentCheckInterval = setInterval(async () => {
    if (!paymentId) return;

    try {
      const data = await api(`/payment/status/${paymentId}`, { method: "GET" });

      if (data.approved) {
        currentOrderStatus = "paid";
        renderOrderSummary();
        setStatusBox("paymentStatusBox", `✅ Pagamento confirmado!\nStatus: ${data.status}\nPedido liberado.`, "success");
        appendLog("Pagamento confirmado automaticamente.", "success");
        stopPaymentMonitoring();
        await carregarHistoricoPedidos();
      } else {
        currentOrderStatus = "pending_payment";
        renderOrderSummary();
        setStatusBox("paymentStatusBox", `Aguardando pagamento.\nStatus atual: ${data.status || "desconhecido"}`, "warning");
      }
    } catch (error) {
      appendLog(`Erro ao verificar pagamento: ${error.message}`, "error");
    }
  }, 5000);
}

async function carregarHistoricoPedidos() {
  const listEl = byId("ordersList");
  if (!listEl || !currentUser?.email) return;

  try {
    const orders = await api(`/orders?user_email=${encodeURIComponent(currentUser.email)}`, {
      method: "GET"
    });

    if (!Array.isArray(orders) || orders.length === 0) {
      listEl.innerHTML = `
        <div class="order-card">
          <strong>Nenhum pedido ainda</strong>
          <div class="order-meta">Assim que você criar um pedido, ele aparecerá aqui.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = orders.map((order) => `
      <div class="order-card">
        <strong>Pedido #${order.id}</strong>
        <div class="order-meta">
          <div><b>Status:</b> ${order.status}</div>
          <div><b>Valor:</b> R$ ${Number(order.amount || 0).toFixed(2)}</div>
          <div><b>Descrição:</b> ${order.description || "Passeio AmigoPet"}</div>
          <div><b>Payment ID:</b> ${order.payment_id ?? "não gerado"}</div>
        </div>
      </div>
    `).join("");
  } catch (error) {
    listEl.innerHTML = `
      <div class="order-card">
        <strong>Erro ao carregar histórico</strong>
        <div class="order-meta">${error.message}</div>
      </div>
    `;
  }
}

async function pagar(event) {
  if (event) event.preventDefault();

  try {
    if (!currentUser) {
      alert("Faça login antes de criar pedido e gerar o pagamento.");
      return;
    }

    const amount = Number(String(byId("paymentAmount")?.value || "30").replace(",", "."));
    const description = (byId("orderDescription")?.value || "").trim() || "Passeio AmigoPet";

    if (!Number.isFinite(amount) || amount <= 0) {
      alert("Digite um valor válido maior que zero.");
      return;
    }

    clearPixDisplay();
    stopPaymentMonitoring();

    setStatusBox("paymentStatusBox", "Criando pedido...", "warning");
    appendLog("Criando pedido comercial...", "warning");

    const order = await api("/orders/create", {
      method: "POST",
      body: JSON.stringify({
        user_email: currentUser.email,
        amount,
        description
      })
    });

    currentOrderId = order.order_id;
    currentOrderStatus = order.status || "pending_payment";
    renderOrderSummary();

    setStatusBox("paymentStatusBox", "Pedido criado. Gerando PIX...", "warning");
    appendLog(`Pedido #${currentOrderId} criado.`, "warning");

    const payment = await api("/payment/pay", {
      method: "POST",
      body: JSON.stringify({
        amount,
        email: currentUser.email,
        order_id: currentOrderId
      })
    });

    paymentId = payment.payment_id || payment.id || null;
    renderOrderSummary();

    renderPixQrCode(payment.qr_code_base64 || "", payment.qr_code || "");

    setStatusBox(
      "paymentStatusBox",
      `PIX gerado com sucesso.\nPedido #${currentOrderId}\nPayment ID: ${paymentId ?? "não retornado"}\nAguardando pagamento...`,
      "warning"
    );

    appendLog("PIX gerado com sucesso e monitoramento iniciado.", "success");
    await carregarHistoricoPedidos();
    monitorarPagamento();
  } catch (error) {
    appendLog(`Erro ao gerar pedido/pagamento: ${error.message}`, "error");
    setStatusBox("paymentStatusBox", `Erro ao gerar pagamento.\n${error.message}`, "error");
    alert(`Erro: ${error.message}`);
  }
}

function handleLogout() {
  stopPaymentMonitoring();
  localStorage.removeItem("amigopet_user");
  currentUser = null;
  paymentId = null;
  currentOrderId = null;
  currentOrderStatus = null;

  updateSessionInfo();
  renderOrderSummary();
  clearPixDisplay();
  setStatusBox("paymentStatusBox", "Sessão encerrada.", "warning");
  appendLog("Usuário saiu da sessão.", "warning");

  const listEl = byId("ordersList");
  if (listEl) {
    listEl.innerHTML = `
      <div class="order-card">
        <strong>Nenhum pedido ainda</strong>
        <div class="order-meta">Assim que você criar um pedido, ele aparecerá aqui.</div>
      </div>
    `;
  }

  showScreen("welcomeScreen");
}

function restoreSession() {
  try {
    const raw = localStorage.getItem("amigopet_user");
    if (!raw) return;

    currentUser = JSON.parse(raw);
    updateSessionInfo();
    renderOrderSummary();
    showScreen("dashboardScreen");
    appendLog("Sessão restaurada.", "success");
    carregarHistoricoPedidos();
  } catch (_) {
    localStorage.removeItem("amigopet_user");
  }
}

function init() {
  byId("loginForm")?.addEventListener("submit", handleLogin);
  byId("registerForm")?.addEventListener("submit", handleRegister);
  byId("payBtn")?.addEventListener("click", pagar);
  byId("checkStatusBtn")?.addEventListener("click", consultarStatusAgora);
  byId("refreshOrdersBtn")?.addEventListener("click", carregarHistoricoPedidos);
  byId("logoutBtn")?.addEventListener("click", handleLogout);
  byId("showWelcomeBtn")?.addEventListener("click", () => showScreen("welcomeScreen"));
  byId("tabLoginBtn")?.addEventListener("click", () => setActiveTab("login"));
  byId("tabRegisterBtn")?.addEventListener("click", () => setActiveTab("register"));

  updateSessionInfo();
  renderOrderSummary();
  restoreSession();
}

document.addEventListener("DOMContentLoaded", init);