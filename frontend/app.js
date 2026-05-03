const API = 'https://amigopet-6td8.onrender.com';
const WS_URL = 'wss://amigopet-6td8.onrender.com/ws';

let currentUser = null;
let currentRequestId = null;
let selectedWalkerId = null;
let lastWalk = null;
let moveStep = 0;
let map = null;
let routeLine = null;
let walkerMarker = null;
let pickupMarker = null;

const $ = (id) => document.getElementById(id);

function toast(msg){
  const el = $('toast');
  if(!el) return alert(msg);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 2800);
}

function safeText(id, value){
  const el = $(id);
  if(el) el.textContent = value;
}

function clearOldSessions(){
  localStorage.removeItem('amigopet_user');
  localStorage.removeItem('amigopet_cliente_user');
}

function setLoggedUI(){
  const logged = $('loggedUser');
  const requestBtn = $('btnRequest');
  const trackingBtn = $('btnTracking');
  const logoutBtn = $('logoutBtn');

  if(currentUser && currentUser.role === 'client'){
    if(logged) logged.innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>Cliente</strong>`;
    if(requestBtn) requestBtn.style.display = 'inline-flex';
    if(trackingBtn) trackingBtn.style.display = 'inline-flex';
    if(logoutBtn) logoutBtn.style.display = 'inline-flex';
  }else{
    if(logged) logged.textContent = 'Nenhum cliente conectado.';
    if(requestBtn) requestBtn.style.display = 'none';
    if(trackingBtn) trackingBtn.style.display = 'none';
    if(logoutBtn) logoutBtn.style.display = 'none';
  }
}

function requireClient(){
  if(currentUser && currentUser.role === 'client') return true;
  toast('Faça login como cliente para acessar esta área.');
  showView('home', true);
  return false;
}

function fillClientDemo(){
  $('loginEmail').value = 'cliente@amigopet.com';
  $('loginPassword').value = '123456';
  toast('Conta teste preenchida.');
}

function toggleRegister(){
  const box = $('registerBox');
  if(box) box.classList.toggle('open');
}

function logout(){
  currentUser = null;
  currentRequestId = null;
  selectedWalkerId = null;
  lastWalk = null;
  clearOldSessions();
  setLoggedUI();
  showView('home', true);
  toast('Sessão encerrada.');
}

function showView(id, force=false){
  if((id === 'request' || id === 'tracking') && !requireClient()){
    id = 'home';
  }

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const view = $(id);
  if(view) view.classList.add('active');

  const btn = document.querySelector(`[data-view="${id}"]`);
  if(btn) btn.classList.add('active');

  if(id === 'request') refreshAll().catch(()=>{});
  if(id === 'tracking') setTimeout(() => { initMap(); if(lastWalk) renderMap(lastWalk); }, 250);
}

document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => showView(btn.dataset.view));
});

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

async function login(){
  try{
    const email = $('loginEmail').value.trim();
    const password = $('loginPassword').value.trim();

    if(!email || !password) return toast('Preencha e-mail e senha.');

    const user = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });

    if(user.role !== 'client'){
      currentUser = null;
      clearOldSessions();
      setLoggedUI();
      return toast('Este app é exclusivo para clientes.');
    }

    currentUser = user;
    clearOldSessions();
    setLoggedUI();
    toast('Login realizado.');
    await refreshAll();
    showView('request', true);
  }catch(err){
    toast(err.message || 'Não foi possível entrar.');
  }
}

async function registerClient(){
  try{
    const data = {
      full_name: $('registerName').value.trim(),
      email: $('registerEmail').value.trim(),
      password: $('registerPassword').value.trim() || '123456',
      role: 'client',
      phone: $('registerPhone').value.trim(),
      address: $('registerAddress').value.trim(),
      neighborhood: $('registerNeighborhood').value.trim(),
      city: $('registerCity').value.trim(),
      photo: '',
      document: '',
      bio: ''
    };

    if(!data.full_name || !data.email || !data.password){
      return toast('Preencha nome, e-mail e senha.');
    }

    await api('/api/auth/register', {
      method:'POST',
      body: JSON.stringify(data)
    });

    $('loginEmail').value = data.email;
    $('loginPassword').value = data.password;
    toast('Conta criada. Entrando...');
    await login();
  }catch(err){
    toast(err.message || 'Não foi possível criar a conta.');
  }
}

async function createPet(){
  try{
    if(!requireClient()) return;

    const name = $('petName').value.trim();
    const photo = $('petPhoto').value.trim();

    if(!name) return toast('Informe o nome do pet.');
    if(!photo) return toast('A foto do pet é obrigatória. Cole uma URL de imagem.');

    const pet = await api('/api/pets', {
      method:'POST',
      body: JSON.stringify({
        owner_id: currentUser.id,
        name,
        breed: $('petBreed').value,
        size: $('petSize').value,
        age: $('petAge').value,
        photo,
        notes: $('petNotes').value
      })
    });

    toast(`Pet ${pet.name} cadastrado com foto.`);
    await refreshAll();
  }catch(err){
    toast(err.message);
  }
}

function selectWalker(id){
  selectedWalkerId = id;
  if($('walkerSelect')) $('walkerSelect').value = String(id);
  document.querySelectorAll('.walker-card').forEach(c => c.style.outline = 'none');
  const card = document.querySelector(`[data-walker-card="${id}"]`);
  if(card) card.style.outline = '3px solid #14b8a6';
  toast('Passeador selecionado.');
}

async function createWalk(){
  try{
    if(!requireClient()) return;

    const data = {
      client_id: currentUser.id,
      walker_id: Number($('walkerSelect').value) || selectedWalkerId || null,
      pet_id: Number($('petSelect').value) || null,
      address: $('address').value,
      pickup_lat: -22.5884,
      pickup_lng: -43.1847,
      duration_minutes: Number($('duration').value),
      dogs_count: Number($('dogsCount').value),
      notes: 'Convite criado pelo cliente.'
    };

    if(!data.pet_id) return toast('Escolha um pet antes de solicitar o passeio.');
    if(!data.walker_id) return toast('Escolha um passeador antes de solicitar o passeio.');

    const walk = await api('/api/walks', {
      method:'POST',
      body: JSON.stringify(data)
    });

    currentRequestId = walk.id;
    lastWalk = walk;
    renderCurrentWalk(walk);
    renderMap(walk);
    toast(`Convite #${walk.id} enviado. R$ ${Number(walk.estimated_price).toFixed(2)}`);
    await refreshAll();
    showView('tracking', true);
  }catch(err){
    toast(err.message);
  }
}

async function payWalk(id){
  try{
    if(!requireClient()) return;
    const walk = await api(`/api/walks/${id}/pay`, {method:'POST'});
    lastWalk = walk;
    currentRequestId = id;
    renderCurrentWalk(walk);
    renderMap(walk);
    toast('PIX confirmado.');
    await refreshAll();
  }catch(err){
    toast(err.message);
  }
}

async function simulateMove(){
  if(!requireClient()) return;
  if(!currentRequestId) return toast('Crie ou selecione um pedido primeiro.');

  const target = lastWalk ? [Number(lastWalk.pickup_lat), Number(lastWalk.pickup_lng)] : [-22.5884, -43.1847];
  const start = lastWalk ? [Number(lastWalk.walker_lat), Number(lastWalk.walker_lng)] : [-22.5900, -43.1810];

  moveStep = Math.min(moveStep + 1, 8);
  const progress = moveStep / 8;
  const lat = start[0] + (target[0] - start[0]) * progress;
  const lng = start[1] + (target[1] - start[1]) * progress;

  const walk = await api(`/api/walks/${currentRequestId}/location`, {
    method:'POST',
    body: JSON.stringify({lat, lng})
  });

  lastWalk = walk;
  renderCurrentWalk(walk);
  renderMap(walk);
}

function initMap(){
  const mapEl = $('map');
  if(!mapEl) return;

  if(typeof L === 'undefined'){
    mapEl.innerHTML = '<div class="map-fallback">Mapa indisponível. Verifique a conexão com a internet.</div>';
    return;
  }

  if(map){
    setTimeout(() => map.invalidateSize(), 150);
    return;
  }

  map = L.map('map', { zoomControl: true }).setView([-22.5884, -43.1847], 15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
}

function renderMap(w){
  if(!w) return;

  initMap();
  safeText('gpsStatus', `Acompanhamento: ${Number(w.walker_lat || -22.5900).toFixed(5)}, ${Number(w.walker_lng || -43.1810).toFixed(5)}`);

  if(!map || typeof L === 'undefined') return;

  const walkerPos = [Number(w.walker_lat || -22.5900), Number(w.walker_lng || -43.1810)];
  const pickupPos = [Number(w.pickup_lat || -22.5884), Number(w.pickup_lng || -43.1847)];

  const walkerIcon = L.divIcon({className:'pin walker-pin', html:'🚶', iconSize:[34,34]});
  const pickupIcon = L.divIcon({className:'pin home-pin', html:'🏠', iconSize:[34,34]});

  if(!walkerMarker){
    walkerMarker = L.marker(walkerPos, {icon: walkerIcon}).addTo(map).bindPopup('Passeador');
  }else{
    walkerMarker.setLatLng(walkerPos);
  }

  if(!pickupMarker){
    pickupMarker = L.marker(pickupPos, {icon: pickupIcon}).addTo(map).bindPopup('Cliente / retirada');
  }else{
    pickupMarker.setLatLng(pickupPos);
  }

  if(routeLine) routeLine.remove();
  routeLine = L.polyline([walkerPos, pickupPos], {weight:5, opacity:0.85, dashArray:'8, 10'}).addTo(map);

  const bounds = L.latLngBounds([walkerPos, pickupPos]).pad(0.25);
  map.fitBounds(bounds);
  setTimeout(() => map.invalidateSize(), 150);
}

function renderCurrentWalk(w){
  if(!w) return;

  const box = $('currentWalkBox');
  if(box){
    box.innerHTML = `<strong>#${w.id} • ${w.pet || 'Pet'}</strong><br>
    Cliente: ${w.client}<br>
    Passeador: ${w.walker}<br>
    Status: <span class="badge ${w.status}">${w.status}</span><br>
    Pagamento: <span class="badge ${w.payment_status}">${w.payment_status}</span><br>
    Distância: ${w.distance_km} km • ${w.duration_minutes} min • R$ ${Number(w.estimated_price).toFixed(2)}<br>
    Localização passeador: ${Number(w.walker_lat || -22.5900).toFixed(5)}, ${Number(w.walker_lng || -43.1810).toFixed(5)}`;
  }

  const pixBox = $('pixBox');
  if(pixBox) pixBox.textContent = w.pix_code || 'PIX será gerado ao criar o pedido.';

  renderMap(w);
}

function walkItem(w){
  const timer = w.seconds_left > 0 ? `<span class="badge convite_enviado">⏱ ${Math.floor(w.seconds_left/60)}:${String(w.seconds_left%60).padStart(2,'0')}</span>` : '';

  return `<div class="item">
    <div class="item-head">
      <div>
        <strong>#${w.id} • ${w.pet || 'Pet não informado'}</strong><br>
        <span class="muted">${w.client} → ${w.walker}</span><br>
        <span>${w.address}</span>
      </div>
      <div>
        <span class="badge ${w.status}">${w.status}</span>
        <span class="badge ${w.payment_status}">${w.payment_status}</span>
        ${timer}
      </div>
    </div>
    <div class="muted">${w.duration_minutes} min • ${w.dogs_count} cão(s) • ${w.distance_km} km • R$ ${Number(w.estimated_price).toFixed(2)}</div>
    <div class="actions">
      <button class="warn" type="button" onclick="payWalk(${w.id})">Confirmar PIX</button>
      <button type="button" onclick="openChat(${w.id})">Chat</button>
      <button type="button" onclick="currentRequestId=${w.id}; loadWalk(${w.id}); showView('tracking', true)">Mapa</button>
    </div>
  </div>`;
}

async function loadWalk(id){
  const walk = await api(`/api/walks/${id}`);
  currentRequestId = walk.id;
  lastWalk = walk;
  renderCurrentWalk(walk);
  renderMap(walk);
}

async function refreshAll(){
  if(!currentUser || currentUser.role !== 'client') return;

  let walkers = [];
  let walks = [];
  let pets = [];

  try{
    [walkers, walks, pets] = await Promise.all([
      api('/api/users?role=walker'),
      api('/api/walks'),
      api(`/api/pets?owner_id=${currentUser.id}`)
    ]);
  }catch(e){
    return;
  }

  if($('walkerSelect')){
    $('walkerSelect').innerHTML = `<option value="">Escolha um passeador</option>` + walkers.map(w =>
      `<option value="${w.id}">${w.full_name} • ⭐ ${w.rating} • ${w.neighborhood || '-'}</option>`
    ).join('');
  }

  if($('walkerCards')){
    $('walkerCards').innerHTML = walkers.map(w => `<div class="walker-card" data-walker-card="${w.id}">
      <div class="avatar">🚶</div>
      <strong>${w.full_name}</strong>
      <span>⭐ ${w.rating} • ${w.neighborhood || '-'}</span>
      <p class="muted">${w.bio || 'Passeador disponível.'}</p>
      <button type="button" onclick="selectWalker(${w.id})">Escolher</button>
    </div>`).join('');
  }

  if($('petSelect')){
    $('petSelect').innerHTML = `<option value="">Escolha o pet</option>` + pets.map(p =>
      `<option value="${p.id}">${p.name} • ${p.size}</option>`
    ).join('');
  }

  const myWalks = walks.filter(w => w.client_id === currentUser.id);

  if(!lastWalk && myWalks[0]){
    lastWalk = myWalks[0];
    currentRequestId = myWalks[0].id;
    renderCurrentWalk(myWalks[0]);
    renderMap(myWalks[0]);
  }
}

function toggleChat(){
  const box = $('chatBox');
  if(!box) return;
  box.classList.toggle('open');
  if(box.classList.contains('open')) loadMessages();
}

async function openChat(requestId){
  currentRequestId = requestId;
  $('chatBox').classList.add('open');
  await loadMessages();
}

async function loadMessages(){
  if(!currentRequestId){
    $('chatMessages').innerHTML = '<div class="notice">Abra uma solicitação primeiro.</div>';
    return;
  }

  const msgs = await api(`/api/messages/${currentRequestId}`);

  $('chatMessages').innerHTML = msgs.length
    ? msgs.map(m => `<div class="bubble">${m.text}<br><small>${new Date(m.created_at).toLocaleString('pt-BR')}</small></div>`).join('')
    : '<div class="notice">Nenhuma mensagem ainda.</div>';
}

async function sendMessage(){
  try{
    if(!requireClient()) return;
    if(!currentRequestId) return toast('Abra uma solicitação primeiro.');

    const text = $('chatText').value.trim();
    if(!text) return;

    await api('/api/messages', {
      method:'POST',
      body: JSON.stringify({request_id: currentRequestId, sender_id: currentUser.id, text})
    });

    $('chatText').value = '';
    await loadMessages();
  }catch(err){
    toast(err.message);
  }
}

function connectWS(){
  try{
    const ws = new WebSocket(WS_URL);

    ws.onmessage = async (ev) => {
      const data = JSON.parse(ev.data);

      const labels = {
        walk_created:'Novo convite criado',
        walk_accepted:'Passeador aceitou',
        walk_rejected:'Passeador recusou',
        walk_expired:'⛔ Tempo esgotado',
        payment_confirmed:'Pagamento confirmado',
        walk_started:'Passeio iniciado',
        walk_finished:'Passeio finalizado',
        location_updated:'Localização do passeador atualizada',
        message:'Nova mensagem'
      };

      if(data.type) toast(labels[data.type] || 'Atualização recebida');

      if(data.walk && currentUser && data.walk.client_id === currentUser.id){
        lastWalk = data.walk;
        currentRequestId = data.walk.id;
        renderCurrentWalk(data.walk);
        renderMap(data.walk);
      }

      if(currentUser) await refreshAll();
      if(currentRequestId) loadMessages();
    };

    ws.onclose = () => setTimeout(connectWS, 2500);
  }catch(e){}
}

clearOldSessions();
setLoggedUI();
showView('home', true);
connectWS();
