// 🔥 CADASTRO COM TELEFONE
async function registerUser() {
  try {
    const payload = {
      full_name: byId("full_name").value,
      email: byId("email").value,
      password: byId("password").value,
      role: "client",
      phone: byId("phone")?.value || "",
      neighborhood: byId("neighborhood").value,
      city: byId("city").value,
      address: byId("address").value
    };

    await api("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    alert("Conta criada com sucesso!");
  } catch (err) {
    alert(err.message);
  }
}

// 🔥 LISTA DE PETS CORRIGIDA
async function loadPets() {
  if (!currentUser?.id) return;

  try {
    const pets = await api(`/pets/${currentUser.id}`);
    renderPets(pets);
  } catch (err) {
    console.log(err.message);
  }
}

function renderPets(pets) {
  const box = document.getElementById("petList");
  if (!box) return;

  box.innerHTML = "";

  pets.forEach((pet) => {
    const div = document.createElement("div");
    div.className = "pet-mini-card";

    div.innerHTML = `
      <img src="${pet.photo_url || ''}" />
      <div>
        <div class="pet-mini-title">${pet.name}</div>
        <div class="pet-mini-meta">${pet.breed || ""}</div>
      </div>
    `;

    box.appendChild(div);
  });
}