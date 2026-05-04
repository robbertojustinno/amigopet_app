const API = "https://amigopet-6td8.onrender.com";

let userId = null;
let photoBase64 = "";
let petPhoto = "";

// NAV
function goHome() {
  hideAll();
  document.getElementById("home").classList.remove("hidden");
}

function showLogin() {
  hideAll();
  document.getElementById("login").classList.remove("hidden");
}

function showRegister() {
  hideAll();
  document.getElementById("register").classList.remove("hidden");
}

function showPet() {
  hideAll();
  document.getElementById("pet").classList.remove("hidden");
}

function backDashboard() {
  hideAll();
  document.getElementById("dashboard").classList.remove("hidden");
}

function hideAll() {
  document.querySelectorAll("section").forEach(s => s.classList.add("hidden"));
}

// LOGIN
async function login() {
  const email = loginEmail.value;
  const password = loginPassword.value;

  const res = await fetch(API + "/auth/login", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({email, password})
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

// REGISTER
async function register() {
  const body = {
    full_name: r_name.value,
    email: r_email.value,
    password: r_pass.value,
    phone: r_phone.value,
    address: r_address.value,
    city: r_city.value,
    state: r_state.value,
    photo: photoBase64
  };

  const res = await fetch(API + "/auth/register-client", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body)
  });

  const data = await res.json();

  if (data.ok) {
    alert("Conta criada!");
    goHome();
  } else {
    alert("Erro cadastro");
  }
}

// PET
async function createPet() {
  const body = {
    owner_id: userId,
    name: p_name.value,
    breed: p_breed.value,
    size: p_size.value,
    age: p_age.value,
    photo: petPhoto
  };

  const res = await fetch(API + "/api/pets", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body)
  });

  const data = await res.json();

  if (data.ok) {
    alert("Pet cadastrado!");
    backDashboard();
  } else {
    alert("Erro pet");
  }
}

// IMAGE
function previewImage(event) {
  const reader = new FileReader();
  reader.onload = () => {
    photoBase64 = reader.result;
    preview.src = reader.result;
  };
  reader.readAsDataURL(event.target.files[0]);
}

function previewPet(event) {
  const reader = new FileReader();
  reader.onload = () => {
    petPhoto = reader.result;
    previewPet.src = reader.result;
  };
  reader.readAsDataURL(event.target.files[0]);
}

// LOGOUT
function logout() {
  userId = null;
  goHome();
}

// INIT
goHome();