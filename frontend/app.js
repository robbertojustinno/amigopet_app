const API = "https://amigopet-6td8.onrender.com";

let userId = null;
let photoBase64 = "";
let petPhoto = "";

// ================= NAV =================
function goHome() {
  hideAll();

  if (userId) {
    dashboard.classList.remove("hidden");
  } else {
    home.classList.remove("hidden");
  }
}

function showLogin() {
  hideAll();
  login.classList.remove("hidden");
}

function showRegister() {
  hideAll();
  register.classList.remove("hidden");
}

function showPet() {
  hideAll();
  pet.classList.remove("hidden");
}

function backDashboard() {
  hideAll();
  dashboard.classList.remove("hidden");
}

function hideAll() {
  document.querySelectorAll("section").forEach(s => s.classList.add("hidden"));
}

// ================= LOGIN =================
async function login() {
  const res = await fetch(API + "/auth/login", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      email: loginEmail.value,
      password: loginPassword.value
    })
  });

  const data = await res.json();

  if (data.id) {
    userId = data.id;
    userName.innerText = data.name;
    hideAll();
    dashboard.classList.remove("hidden");
  } else {
    alert("Erro login");
  }
}

// ================= REGISTER =================
async function register() {
  if (!photoBase64) {
    alert("Foto obrigatória");
    return;
  }

  const res = await fetch(API + "/auth/register-client", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      full_name: r_name.value,
      email: r_email.value,
      password: r_pass.value,
      phone: r_phone.value,
      address: r_address.value,
      city: r_city.value,
      state: r_state.value,
      photo: photoBase64
    })
  });

  const data = await res.json();

  if (data.ok) {
    alert("Conta criada!");
    logout();
  } else {
    alert("Erro cadastro");
  }
}

// ================= PET =================
async function createPet() {
  if (!petPhoto) {
    alert("Foto do pet obrigatória");
    return;
  }

  const res = await fetch(API + "/api/pets", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      owner_id: userId,
      name: p_name.value,
      breed: p_breed.value,
      size: p_size.value,
      age: p_age.value,
      photo: petPhoto
    })
  });

  const data = await res.json();

  if (data.ok) {
    alert("Pet cadastrado!");
    backDashboard();
  } else {
    alert("Erro pet");
  }
}

// ================= FOTO CLIENTE =================
function previewImage(event) {
  const file = event.target.files[0];

  if (!file) return;

  const reader = new FileReader();

  reader.onload = () => {
    photoBase64 = reader.result;
    preview.src = reader.result;
  };

  reader.readAsDataURL(file);
}

// ================= FOTO PET =================
function previewPet(event) {
  const file = event.target.files[0];

  if (!file) return;

  const reader = new FileReader();

  reader.onload = () => {
    petPhoto = reader.result;
    previewPet.src = reader.result;
  };

  reader.readAsDataURL(file);
}

// ================= LOGOUT =================
function logout() {
  userId = null;
  photoBase64 = "";
  petPhoto = "";

  goHome();
}

// ================= INIT =================
logout();