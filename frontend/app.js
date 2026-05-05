const API = "https://amigopet-6td8.onrender.com";

let userId = null;
let currentUser = null;
let photoBase64 = "";
let petPhoto = "";

function el(id) {
  return document.getElementById(id);
}

function toast(message) {
  const box = el("toast");
  if (!box) {
    alert(message);
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
  setTimeout(() => box.classList.add("hidden"), 2800);
}

function showSection(sectionId) {
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.add("hidden");
  });

  const section = el(sectionId);
  if (section) {
    section.classList.remove("hidden");
  }
}

function goHome() {
  showSection(userId ? "dashboard" : "home");
}

function showLoginScreen() {
  showSection("login");
}

function showRegisterScreen() {
  showSection("register");
}

function showPetScreen() {
  if (!userId) {
    toast("Faça login antes de cadastrar um pet.");
    showSection("login");
    return;
  }
  showSection("pet");
}

function logoutUser() {
  userId = null;
  currentUser = null;
  photoBase64 = "";
  petPhoto = "";

  const userName = el("userName");
  if (userName) userName.textContent = "";

  showSection("home");
}

async function loginClient() {
  const email = el("loginEmail")?.value.trim() || "";
  const password = el("loginPassword")?.value.trim() || "";

  if (!email || !password) {
    toast("Preencha email e senha.");
    return;
  }

  try {
    const res = await fetch(API + "/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ email, password })
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      toast(data.detail || "Erro ao fazer login.");
      return;
    }

    if (data.role && data.role !== "client") {
      toast("Este app é exclusivo para clientes.");
      return;
    }

    userId = data.id;
    currentUser = data;

    const userName = el("userName");
    if (userName) {
      userName.textContent = data.full_name || data.name || "Cliente";
    }

    const userPhoto = el("userPhoto");
    if (userPhoto) {
      userPhoto.src = data.photo || "https://api.dicebear.com/8.x/initials/svg?seed=Cliente";
    }

    const dashboardTitle = el("dashboardTitle");
    if (dashboardTitle) {
      dashboardTitle.textContent = "Olá, " + (data.full_name || "Cliente").split(" ")[0];
    }

    showSection("dashboard");
  } catch (error) {
    toast("Erro de conexão ao fazer login.");
  }
}

async function registerClient() {
  if (!photoBase64) {
    toast("A foto do cliente é obrigatória.");
    return;
  }

  const body = {
    full_name: el("r_name")?.value.trim() || "",
    email: el("r_email")?.value.trim() || "",
    password: el("r_pass")?.value.trim() || "",
    role: "client",
    phone: el("r_phone")?.value.trim() || "",
    address: el("r_address")?.value.trim() || "",
    neighborhood: "",
    city: el("r_city")?.value.trim() || "",
    state: el("r_state")?.value.trim() || "RJ",
    photo: photoBase64,
    document: "",
    bio: ""
  };

  if (!body.full_name || !body.email || !body.password || !body.phone || !body.address || !body.city || !body.state) {
    toast("Preencha todos os campos obrigatórios.");
    return;
  }

  if (body.password.length < 6) {
    toast("A senha deve ter pelo menos 6 caracteres.");
    return;
  }

  try {
    const res = await fetch(API + "/api/auth/register", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      toast(data.detail || "Erro ao criar conta.");
      return;
    }

    toast("Conta criada com sucesso! Agora faça login.");
    photoBase64 = "";
    const preview = el("preview");
    if (preview) preview.removeAttribute("src");
    showSection("login");
  } catch (error) {
    toast("Erro de conexão ao criar conta.");
  }
}

async function createPet() {
  if (!userId) {
    toast("Faça login antes de cadastrar um pet.");
    showSection("login");
    return;
  }

  if (!petPhoto) {
    toast("A foto do pet é obrigatória.");
    return;
  }

  const body = {
    owner_id: userId,
    name: el("p_name")?.value.trim() || "",
    breed: el("p_breed")?.value.trim() || "",
    size: el("p_size")?.value.trim() || "Médio",
    age: el("p_age")?.value.trim() || "",
    photo: petPhoto,
    notes: "",
    dog_count: 1
  };

  if (!body.name) {
    toast("Informe o nome do pet.");
    return;
  }

  try {
    const res = await fetch(API + "/api/pets", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      toast(data.detail || "Erro ao cadastrar pet.");
      return;
    }

    toast("Pet cadastrado com sucesso!");
    petPhoto = "";
    const previewPetImg = el("previewPet");
    if (previewPetImg) previewPetImg.removeAttribute("src");
    showSection("dashboard");
  } catch (error) {
    toast("Erro de conexão ao cadastrar pet.");
  }
}

function readImageFile(file, callback) {
  if (!file) return;

  if (!file.type.startsWith("image/")) {
    toast("Escolha uma imagem válida.");
    return;
  }

  if (file.size > 2000000) {
    toast("Use uma imagem menor que 2 MB.");
    return;
  }

  const reader = new FileReader();
  reader.onload = () => callback(reader.result);
  reader.onerror = () => toast("Não foi possível carregar a imagem.");
  reader.readAsDataURL(file);
}

function handleClientPhoto(event) {
  const file = event.target.files && event.target.files[0];
  readImageFile(file, (result) => {
    photoBase64 = result;
    const preview = el("preview");
    if (preview) {
      preview.src = result;
      preview.style.display = "block";
    }
  });
}

function handlePetPhoto(event) {
  const file = event.target.files && event.target.files[0];
  readImageFile(file, (result) => {
    petPhoto = result;
    const previewPetImg = el("previewPet");
    if (previewPetImg) {
      previewPetImg.src = result;
      previewPetImg.style.display = "block";
    }
  });
}



async function apiGet(path) {
  const res = await fetch(API + path);
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.detail || "Erro na requisição.");
  }

  return data;
}

function formatApiError(data) {
  if (!data) return "Erro na requisição.";

  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.join(".") : "campo";
      return `${field}: ${item.msg || "inválido"}`;
    }).join(" | ");
  }

  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;

  try {
    return JSON.stringify(data);
  } catch (error) {
    return "Erro na requisição.";
  }
}

async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(formatApiError(data));
  }

  return data;
}

function fillSelect(selectId, items, labelFn) {
  const select = el(selectId);
  if (!select) return;

  if (!items.length) {
    select.innerHTML = '<option value="">Nenhum item disponível</option>';
    return;
  }

  select.innerHTML = '<option value="">Selecione</option>' + items.map((item) => {
    return `<option value="${item.id}">${labelFn(item)}</option>`;
  }).join("");
}

async function openWalkRequest() {
  if (!userId) {
    toast("Faça login para solicitar um passeio.");
    showSection("login");
    return;
  }

  try {
    const [pets, walkers] = await Promise.all([
      apiGet(`/api/pets?owner_id=${userId}`),
      apiGet("/api/users?role=walker")
    ]);

    fillSelect("walkPet", pets, (p) => `${p.name} • ${p.size || "Porte não informado"}`);
    fillSelect("walkWalker", walkers, (w) => `${w.full_name} • ⭐ ${w.rating || "5.0"} • ${w.neighborhood || "Região"}`);

    const addressInput = el("walkAddress");
    if (addressInput && currentUser) {
      addressInput.value = currentUser.address || "";
    }

    showSection("walkRequest");
  } catch (error) {
    toast(error.message || "Não foi possível carregar a solicitação.");
  }
}

async function createWalkRequest() {
  if (!userId) {
    toast("Faça login para solicitar um passeio.");
    showSection("login");
    return;
  }

  const petId = Number(el("walkPet")?.value || 0);
  const walkerId = Number(el("walkWalker")?.value || 0);
  const duration = Number(el("walkDuration")?.value || 30);
  const dogsCount = Number(el("walkDogsCount")?.value || 1);
  const address = el("walkAddress")?.value.trim() || "";

  if (!petId) {
    toast("Escolha um pet.");
    return;
  }

  if (!walkerId) {
    toast("Escolha um passeador.");
    return;
  }

  if (!address) {
    toast("Informe o endereço de retirada.");
    return;
  }

  try {
    const walk = await apiPost("/api/walks", {
      client_id: Number(userId),
      walker_id: Number(walkerId),
      pet_id: Number(petId),
      address: String(address),
      pickup_lat: Number(currentUser?.lat || -22.5884),
      pickup_lng: Number(currentUser?.lng || -43.1847),
      duration_minutes: Number(duration),
      dogs_count: Number(dogsCount || 1),
      notes: "Solicitação criada pelo app cliente."
    });

    toast(`Convite enviado! Valor estimado: R$ ${Number(walk.estimated_price || 0).toFixed(2)}`);
    await openOrders();
  } catch (error) {
    toast(error.message || "Não foi possível criar o passeio.");
  }
}

function orderCard(order) {
  const price = Number(order.estimated_price || 0).toFixed(2);
  return `
    <div class="order-card">
      <strong>#${order.id} • ${order.pet || "Pet"}</strong>
      <span>Status: ${order.status || "-"}</span>
      <span>Pagamento: ${order.payment_status || "-"}</span>
      <span>Passeador: ${order.walker || "Aguardando"}</span>
      <span>${order.duration_minutes || 30} min • ${order.dogs_count || 1} cão(s) • R$ ${price}</span>
    </div>
  `;
}

async function openOrders() {
  if (!userId) {
    toast("Faça login para ver seus pedidos.");
    showSection("login");
    return;
  }

  const list = el("ordersList");
  if (list) list.innerHTML = '<div class="notice">Carregando pedidos...</div>';

  try {
    const allOrders = await apiGet("/api/walks");
    const myOrders = allOrders.filter((order) => Number(order.client_id) === Number(userId));

    if (list) {
      list.innerHTML = myOrders.length
        ? myOrders.map(orderCard).join("")
        : '<div class="notice">Você ainda não criou nenhum pedido.</div>';
    }

    showSection("orders");
  } catch (error) {
    toast(error.message || "Não foi possível carregar pedidos.");
  }
}

function showComingSoon(title, text) {
  const titleEl = el("comingSoonTitle");
  const textEl = el("comingSoonText");

  if (titleEl) titleEl.textContent = title;
  if (textEl) textEl.textContent = text;

  showSection("comingSoon");
}

function bindEvents() {
  const bindings = [
    ["btnShowLogin", showLoginScreen],
    ["btnShowRegister", showRegisterScreen],
    ["btnLogin", loginClient],
    ["btnLoginBack", goHome],
    ["btnRegister", registerClient],
    ["btnRegisterBack", goHome],
    ["btnShowPet", showPetScreen],
    ["btnLogout", logoutUser],
    ["btnCreatePet", createPet],
    ["btnPetBack", () => showSection("dashboard")],
    ["btnRequestWalk", openWalkRequest],
    ["btnMyOrders", openOrders],
    ["btnProfile", () => showComingSoon("Perfil", "Aqui ficará a ficha profissional do cliente com foto, telefone e endereço.")],
    ["btnComingSoonBack", () => showSection("dashboard")],
    ["btnCreateWalk", createWalkRequest],
    ["btnWalkBack", () => showSection("dashboard")],
    ["btnOrdersBack", () => showSection("dashboard")]
  ];

  bindings.forEach(([id, handler]) => {
    const button = el(id);
    if (button) button.addEventListener("click", handler);
  });

  const clientPhotoInput = el("r_photo");
  if (clientPhotoInput) clientPhotoInput.addEventListener("change", handleClientPhoto);

  const petPhotoInput = el("p_photo");
  if (petPhotoInput) petPhotoInput.addEventListener("change", handlePetPhoto);
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  logoutUser();
});
