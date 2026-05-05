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
let clientPhotoData = '';
let petPhotoData = '';

const $ = (id) => document.getElementById(id);

function toast(msg){
  const el = $('toast');
  if(!el) return alert(msg);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3200);
}

function safeText(id, value){
  const el = $(id);
  if(el) el.textContent = value;
}

function clearSessions(){
  localStorage.removeItem('amigopet_user');
  localStorage.removeItem('amigopet_cliente_user');
}

function setAuthMode(mode){
  ['login','register','verify'].forEach(name => {
    const tab = $(`${name}Tab`);
    const panel = $(`${name}Panel`);
    if(tab) tab.classList.toggle('active', name === mode);
    if(panel) panel.classList.toggle('active', name === mode);
  });
}

function setLoggedUI(){
  const logged = $('loggedUser');
  const profileChip = $('profileChip');
  const profilePhoto = $('profilePhoto');
  const profilePhotoLarge = $('profilePhotoLarge');
  const profileName = $('profileName');

  const loggedIn = currentUser && currentUser.role === 'client';

  ['btnPet','btnWalk','btnMap','logoutBtn'].forEach(id => {
    const el = $(id);
    if(el) el.classList.toggle('hidden', !loggedIn);
  });

  if(profileChip) profileChip.classList.toggle('hidden', !loggedIn);

  if(loggedIn){
    if(logged) logged.innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>Cliente</strong>`;
    if(profileName) profileName.textContent = currentUser.full_name;
    if(profilePhoto) profilePhoto.src = currentUser.photo || currentUser.profile_photo || '';
    if(profilePhotoLarge) profilePhotoLarge.src = currentUser.photo || currentUser.profile_photo || '';
    renderClientDetails();
  }else{
    if(logged) logged.textContent = 'Nenhum cliente conectado.';
  }
}

function requireClient(){
  if(currentUser && currentUser.role === 'client') return true;
  toast('Faça login como cliente para acessar esta área.');
  showView('home', true);
  return false;
}

function showView(id, force=false){
  if(['pet','walk','tracking'].includes(id) && !requireClient()){
    id = 'home';
  }

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const view = $(id);
  if(view) view.classList.add('active');

  const btn = document.querySelector(`[data-view="${id}"]`);
  if(btn) btn.classList.add('active');

  if(currentUser) refreshAll().catch(()=>{});
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

function fileToDataUrl(file){
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Não foi possível ler a imagem.'));
    reader.readAsDataURL(file);
  });
}

async function handleClientPhoto(event){
  const file = event.target.files?.[0];
  if(!file) return;
  if(file.size > 1_500_000){
    event.target.value = '';
    return toast('Use uma imagem do cliente menor que 1,5 MB.');
  }
  clientPhotoData = await fileToDataUrl(file);
  const img = $('clientPhotoPreview');
  if(img){
    img.src = clientPhotoData;
    img.classList.remove('hidden');
  }
  safeText('clientPhotoStatus', 'Foto selecionada.');
}

async function handlePetPhoto(event){
  const file = event.target.files?.[0];
  if(!file) return;
  if(file.size > 1_500_000){
    event.target.value = '';
    return toast('Use uma imagem do pet menor que 1,5 MB.');
  }
  petPhotoData = await fileToDataUrl(file);
  const img = $('petPhotoPreview');
  if(img){
    img.src = petPhotoData;
    img.classList.remove('hidden');
  }
  safeText('petPhotoStatus', 'Foto do pet selecionada.');
}

function fillClientDemo(){
  $('loginEmail').value = 'cliente@amigopet.com';
  $('loginPassword').value = '123456';
  setAuthMode('login');
  toast('Conta teste preenchida.');
}

async function registerClient(){
  try{
    const data = {
      full_name: $('registerName').value.trim(),
      email: $('registerEmail').value.trim(),
      password: $('registerPassword').value.trim(),
      phone: $('registerPhone').value.trim(),
      photo: clientPhotoData,
      document: $('registerDocument').value.trim(),
      zip_code: $('registerZip').value.trim(),
      street: $('registerStreet').value.trim(),
      number: $('registerNumber').value.trim(),
      complement: $('registerComplement').value.trim(),
      neighborhood: $('registerNeighborhood').value.trim(),
      city: $('registerCity').value.trim(),
      state: $('registerState').value.trim() || 'RJ',
      bio: $('registerBio').value.trim()
    };

    const required = [
      ['full_name','nome completo'],
      ['email','e-mail'],
      ['password','senha'],
      ['phone','telefone'],
      ['photo','foto do cliente'],
      ['street','rua'],
      ['number','número'],
      ['neighborhood','bairro'],
      ['city','cidade']
    ];

    for(const [key,label] of required){
      if(!data[key]) return toast(`Preencha: ${label}.`);
    }

    if(data.password.length < 6) return toast('A senha deve ter no mínimo 6 caracteres.');

    const result = await api('/api/auth/register-client', {
      method:'POST',
      body: JSON.stringify(data)
    });

    $('verifyEmail').value = data.email;
    $('loginEmail').value = data.email;
    setAuthMode('verify');

    if(result.dev_code){
      const box = $('devCodeBox');
      if(box){
        box.classList.remove('hidden');
        box.textContent = `SMTP não configurado. Código de teste: ${result.dev_code}`;
      }
    }

    toast(result.message || 'Cadastro criado. Confirme o código enviado por e-mail.');
  }catch(err){
    toast(err.message || 'Não foi possível criar a conta.');
  }
}

async function verifyCode(){
  try{
    const email = $('verifyEmail').value.trim();
    const code = $('verifyCode').value.trim();

    if(!email || !code) return toast('Informe e-mail e código.');

    const user = await api('/api/auth/verify-code', {
      method:'POST',
      body: JSON.stringify({email, code})
    });

    currentUser = user;
    clearSessions();
    setLoggedUI();
    await refreshAll();
    toast('Conta confirmada com sucesso.');
    showView('pet', true);
  }catch(err){
    toast(err.message || 'Código inválido.');
  }
}

async function resendCode(){
  try{
    const email = $('verifyEmail').value.trim() || $('registerEmail').value.trim();
    if(!email) return toast('Informe o e-mail cadastrado.');

    const result = await api('/api/auth/resend-code', {
      method:'POST',
      body: JSON.stringify({email})
    });

    if(result.dev_code){
      const box = $('devCodeBox');
      if(box){
        box.classList.remove('hidden');
        box.textContent = `SMTP não configurado. Código de teste: ${result.dev_code}`;
      }
    }

    toast(result.message || 'Novo código enviado.');
  }catch(err){
    toast(err.message || 'Não foi possível reenviar.');
  }
}

async function login(){
  try{
    const email = $('loginEmail').value.trim();
    const password = $('loginPassword').value.trim();

    if(!email || !password) return toast('Preencha e-mail e senha.');

    const user = await api('/api/auth/login', {
      method:'POST',
      body: JSON.stringify({email, password})
    });

    if(user.role !== 'client'){
      return toast('Este app é exclusivo para clientes.');
    }

    currentUser = user;
    clearSessions();
    setLoggedUI();
    await refreshAll();
    toast('Login realizado.');
    showView('pet', true);
  }catch(err){
    const msg = err.message || 'Não foi possível entrar.';
    toast(msg);
    if(msg.toLowerCase().includes('confirme')){
      $('verifyEmail').value = $('loginEmail').value.trim();
      setAuthMode('verify');
    }
  }
}

function logout(){
  currentUser = null;
  currentRequestId = null;
  selectedWalkerId = null;
  lastWalk = null;
  clearSessions();
  setLoggedUI();
  showView('home', true);
  toast('Sessão encerrada.');
}

function renderClientDetails(){
  const box = $('clientDetails');
  if(!box || !currentUser) return;
  box.innerHTML = `
    <strong>${currentUser.full_name}</strong><br>
    ${currentUser.email}<br>
    Telefone: ${currentUser.phone || '-'}<br>
    Endereço: ${currentUser.address || '-'}<br>
    Cidade: ${currentUser.city || '-'} / ${currentUser.state || '-'}<br>
    Status: <span class="badge pago">verificado</span>
  `;
  if($('address') && currentUser.address) $('address').value = currentUser.address;
}

async function createPet(){
  try{
    if(!requireClient()) return;

    const data = {
      owner_id: currentUser.id,
      name: $('petName').value.trim(),
      species: 'Cachorro',
      breed: $('petBreed').value.trim(),
      size: $('petSize').value,
      age: $('petAge').value.trim(),
      photo: petPhotoData,
      notes: $('petNotes').value.trim()
    };

    if(!data.name) return toast('Informe o nome do pet.');
    if(!data.photo) return toast('A foto do pet é obrigatória.');
    if(!data.size) return toast('Informe o porte do pet.');

    const pet = await api('/api/pets', {
      method:'POST',
      body: JSON.stringify(data)
    });

    toast(`Pet ${pet.name} cadastrado com sucesso.`);
    petPhotoData = '';
    const preview = $('petPhotoPreview');
    if(preview) preview.classList.add('hidden');
    safeText('petPhotoStatus', 'Nenhuma foto selecionada');
    await refreshAll();
  }catch(err){
    toast(err.message || 'Não foi possível cadastrar o pet.');
  }
}

function renderPets(pets){
  const box = $('myPets');
  if(!box) return;
  if(!pets.length){
    box.innerHTML = '<div class="notice">Nenhum pet cadastrado ainda.</div>';
    return;
  }
  box.innerHTML = pets.map(p => `
    <div class="pet-card">
      <img src="${p.photo || ''}" alt="${p.name}">
      <div>
        <strong>${p.name}</strong><br>
        <span class="muted">${p.breed || 'Raça não informada'} • ${p.size || '-'} • ${p.age || '-'}</span><br>
        <small>${p.notes || ''}</small>
      </div>
    </div>
  `).join('');
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
      pickup_lat: Number(currentUser.lat || -22.5884),
      pickup_lng: Number(currentUser.lng || -43.1847),
      duration_minutes: Number($('duration').value),
      dogs_count: Number($('dogsCount').value),
      notes: 'Convite criado pelo cliente.'
    };

    if(!data.pet_id) return toast('Escolha um pet.');
    if(!data.walker_id) return toast('Escolha um passeador.');
    if(!data.address) return toast('Informe o endereço.');

    const walk = await api('/api/walks', {
      method:'POST',
      body: JSON.stringify(data)
    });

    currentRequestId = walk.id;
    lastWalk = walk;
    renderCurrentWalk(walk);
    renderMap(walk);
    await refreshAll();
    toast(`Convite #${walk.id} enviado. R$ ${Number(walk.estimated_price).toFixed(2)}`);
    showView('tracking', true);
  }catch(err){
    toast(err.message || 'Não foi possível solicitar o passeio.');
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
    toast('Pagamento confirmado.');
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

  renderClientDetails();
  renderPets(pets);

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

  if($('myWalks')){
    $('myWalks').innerHTML = myWalks.length ? myWalks.map(walkItem).join('') : '<div class="notice">Nenhum pedido criado ainda.</div>';
  }

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

clearSessions();
setLoggedUI();
showView('home', true);
connectWS();
