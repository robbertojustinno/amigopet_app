const API = 'https://amigopet-6td8.onrender.com';

let currentUser = null;
let currentRequestId = null;
let selectedWalkerId = null;
let lastWalk = null;
let moveStep = 0;

const $ = (id) => document.getElementById(id);

function toast(msg){
  const el = $('toast');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(()=> el.style.display = 'none', 2800);
}

function fillLogin(){
  $('loginEmail').value = $('quickLogin').value;
  $('loginPassword').value = '123456';
}

function showView(id){
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  $(id).classList.add('active');
  document.querySelectorAll(`[data-view="${id}"]`).forEach(b => b.classList.add('active'));
  refreshAll();
}

document.querySelectorAll('.nav-btn').forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.view)));

async function api(path, options={}){
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  if(!res.ok){
    let detail = 'Erro na requisição';
    try { detail = (await res.json()).detail || detail; } catch(e) {}
    throw new Error(detail);
  }
  return res.json();
}

function connectWS(){
  try{
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://amigopet-6td8.onrender.com/ws`);
    ws.onopen = () => $('liveStatus').textContent = 'Tempo real conectado';
    ws.onmessage = async (ev) => {
      const data = JSON.parse(ev.data);
      const labels = {walk_created:'Novo convite criado', walk_accepted:'Passeador aceitou', walk_rejected:'Passeador recusou', payment_confirmed:'Pagamento confirmado', walk_started:'Passeio iniciado', walk_finished:'Passeio finalizado', location_updated:'Localização atualizada', message:'Nova mensagem'};
      toast(labels[data.type] || 'Atualização recebida');
      if(data.walk){ lastWalk = data.walk; currentRequestId = data.walk.id; renderCurrentWalk(data.walk); }
      await refreshAll();
      if(currentRequestId) loadMessages();
    };
    ws.onclose = () => { $('liveStatus').textContent = 'Reconectando tempo real...'; setTimeout(connectWS, 2500); };
  }catch(e){ $('liveStatus').textContent = 'Tempo real indisponível'; }
}

async function login(){
  try{
    currentUser = await api('/api/auth/login', {method:'POST', body: JSON.stringify({email:$('loginEmail').value, password:$('loginPassword').value})});
    $('loggedUser').innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>${currentUser.role}</strong>`;
    toast('Login realizado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function loginWalker(){
  $('loginEmail').value = 'passeador@amigopet.com';
  $('loginPassword').value = '123456';
  await login();
}

async function createPet(){
  try{
    if(!currentUser) await login();
    const pet = await api('/api/pets', {method:'POST', body: JSON.stringify({
      owner_id: currentUser.id,
      name:$('petName').value,
      breed:$('petBreed').value,
      size:$('petSize').value,
      age:$('petAge').value,
      photo:$('petPhoto').value,
      notes:$('petNotes').value
    })});
    toast(`Pet ${pet.name} cadastrado.`);
    await refreshAll();
  }catch(err){ toast(err.message); }
}

function selectWalker(id){
  selectedWalkerId = id;
  $('walkerSelect').value = String(id);
  document.querySelectorAll('.walker-card').forEach(c => c.style.outline = 'none');
  const card = document.querySelector(`[data-walker-card="${id}"]`);
  if(card) card.style.outline = '3px solid #14b8a6';
  toast('Passeador selecionado.');
}

async function createWalk(){
  try{
    if(!currentUser) await login();
    const data = {
      client_id: currentUser.id,
      walker_id: Number($('walkerSelect').value) || selectedWalkerId || null,
      pet_id: Number($('petSelect').value) || null,
      address: $('address').value,
      duration_minutes: Number($('duration').value),
      dogs_count: Number($('dogsCount').value),
      notes: 'Convite criado pelo cliente.'
    };
    const walk = await api('/api/walks', {method:'POST', body: JSON.stringify(data)});
    currentRequestId = walk.id;
    lastWalk = walk;
    renderCurrentWalk(walk);
    toast(`Convite #${walk.id} enviado. R$ ${walk.estimated_price.toFixed(2)}`);
    await refreshAll();
    showView('tracking');
  }catch(err){ toast(err.message); }
}

// resto do arquivo permanece igual...