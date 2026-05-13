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
let editClientPhotoData = '';
let pricingConfig = null;

const $ = (id) => document.getElementById(id);

function kmBetween(lat1, lng1, lat2, lng2){
  const R = 6371;
  const toRad = (v) => Number(v) * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat/2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng/2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function etaMinutesFromKm(km){
  if(!Number.isFinite(km)) return 0;
  return Math.max(1, Math.ceil((km / 4.5) * 60));
}


function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function photoOrAvatar(user, emoji='🚶'){
  const name = String(user?.full_name || user?.name || 'Passeador').trim();
  const rawPhoto = String(user?.photo || user?.profile_photo || user?.avatar || user?.image || '').trim();
  const fallback = `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(name)}&backgroundColor=ccfbf1,dbeafe,fef3c7`;
  const photo = rawPhoto.length > 8 ? rawPhoto : fallback;
  return `<img src="${escapeHtml(photo)}" alt="${escapeHtml(name)}" style="width:44px;height:44px;border-radius:14px;object-fit:cover;border:2px solid white;box-shadow:0 8px 18px rgba(15,23,42,.14);background:#ccfbf1;" onerror="this.onerror=null;this.src='${escapeHtml(fallback)}';">`;
}

function clientPhotoSrc(user){
  const name = String(user?.full_name || 'Cliente').trim();
  const rawPhoto = String(user?.photo || user?.profile_photo || user?.avatar || user?.image || '').trim();
  const fallback = `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(name)}&backgroundColor=ccfbf1,dbeafe,fef3c7`;
  return rawPhoto.length > 8 ? rawPhoto : fallback;
}

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

  ['btnPet','btnWalk','btnOrders','btnMap','logoutBtn'].forEach(id => {
    const el = $(id);
    if(el) el.classList.toggle('hidden', !loggedIn);
  });

  if(profileChip) profileChip.classList.toggle('hidden', !loggedIn);

  const authCard = $('authCard');
  const loggedHomeCard = $('loggedHomeCard');
  if(authCard) authCard.classList.toggle('hidden', loggedIn);
  if(loggedHomeCard) loggedHomeCard.classList.toggle('hidden', !loggedIn);

  if(loggedIn){
    if(logged) logged.innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>Cliente</strong>`;
    if(profileName) profileName.textContent = currentUser.full_name;
    if(profilePhoto) profilePhoto.src = clientPhotoSrc(currentUser);
    if(profilePhotoLarge) profilePhotoLarge.src = clientPhotoSrc(currentUser);
    renderClientDetails();
    loadPricing().catch(()=>{});
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
  if(['pet','walk','orders','tracking'].includes(id) && !requireClient()){
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

  let data = null;

  try{
    data = await res.json();
  }catch(e){
    data = {};
  }

  if(!res.ok){
    console.error('ERRO API:', path, data); // 👈 LOG REAL

    let detail = 'Erro na requisição';

    if(Array.isArray(data?.detail)){
      detail = data.detail.map(e => e.msg).join(' | ');
    }else if(typeof data?.detail === 'string'){
      detail = data.detail;
    }else{
      detail = JSON.stringify(data);
    }

    throw new Error(detail);
  }

  return data;
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

async function handleEditClientPhoto(event){
  const file = event.target.files?.[0];
  if(!file) return;
  if(file.size > 1_500_000){
    event.target.value = '';
    return toast('Use uma imagem do cliente menor que 1,5 MB.');
  }
  editClientPhotoData = await fileToDataUrl(file);
  const img = $('editClientPhotoPreview');
  if(img){
    img.src = editClientPhotoData;
    img.classList.remove('hidden');
  }
  safeText('editClientPhotoStatus', 'Nova foto selecionada.');
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
    const street = $('registerStreet').value.trim();
    const number = $('registerNumber').value.trim();
    const neighborhood = $('registerNeighborhood').value.trim();
    const city = $('registerCity').value.trim();
    const state = $('registerState').value.trim() || 'RJ';
    const address = [street, number, neighborhood, city, state].filter(Boolean).join(', ');

    const data = {
      full_name: $('registerName').value.trim(),
      email: $('registerEmail').value.trim(),
      password: $('registerPassword').value.trim(),
      role: 'client',
      phone: $('registerPhone').value.trim(),
      photo: clientPhotoData,
      document: $('registerDocument').value.trim(),
      address,
      neighborhood,
      city,
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

    const checkValues = {...data, street, number, neighborhood, city};

    for(const [key,label] of required){
      if(!checkValues[key]) return toast(`Preencha: ${label}.`);
    }

    if(data.password.length < 6) return toast('A senha deve ter no mínimo 6 caracteres.');

    const user = await api('/api/auth/register', {
      method:'POST',
      body: JSON.stringify(data)
    });

    currentUser = user;
    clearSessions();
    setLoggedUI();
    await refreshAll();

    if($('loginEmail')) $('loginEmail').value = '';
    if($('loginPassword')) $('loginPassword').value = '';

    toast('Conta criada com sucesso. Você já está conectado.');
    showView('pet', true);
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
    <strong>${escapeHtml(currentUser.full_name)}</strong><br>
    ${escapeHtml(currentUser.email)}<br>
    Telefone: ${escapeHtml(currentUser.phone || '-')}<br>
    Endereço: ${escapeHtml(currentUser.address || '-')}<br>
    Cidade: ${escapeHtml(currentUser.city || '-')} / ${escapeHtml(currentUser.state || '-')}<br>
    Status: <span class="badge pago">verificado</span>
  `;
  if($('address') && currentUser.address) $('address').value = currentUser.address;
  fillClientEditForm();
}

function fillClientEditForm(){
  if(!currentUser || !$('editClientName')) return;
  $('editClientName').value = currentUser.full_name || '';
  $('editClientPhone').value = currentUser.phone || '';
  $('editClientDocument').value = currentUser.document || '';
  $('editClientZip').value = currentUser.zip_code || '';
  $('editClientStreet').value = currentUser.street || '';
  $('editClientNumber').value = currentUser.number || '';
  $('editClientComplement').value = currentUser.complement || '';
  $('editClientNeighborhood').value = currentUser.neighborhood || '';
  $('editClientCity').value = currentUser.city || '';
  $('editClientState').value = currentUser.state || 'RJ';
  $('editClientBio').value = currentUser.bio || '';
}

function toggleClientEdit(){
  if(!requireClient()) return;
  const box = $('clientEditBox');
  if(!box) return;
  fillClientEditForm();
  box.classList.toggle('hidden');
}

async function updateClientProfile(){
  try{
    if(!requireClient()) return;

    const street = $('editClientStreet').value.trim();
    const number = $('editClientNumber').value.trim();
    const neighborhood = $('editClientNeighborhood').value.trim();
    const city = $('editClientCity').value.trim();
    const state = $('editClientState').value.trim() || 'RJ';
    const address = [street, number, neighborhood, city, state].filter(Boolean).join(', ');

    const data = {
      full_name: $('editClientName').value.trim(),
      phone: $('editClientPhone').value.trim(),
      photo: editClientPhotoData || currentUser.photo || '',
      document: $('editClientDocument').value.trim(),
      address,
      zip_code: $('editClientZip').value.trim(),
      street,
      number,
      complement: $('editClientComplement').value.trim(),
      neighborhood,
      city,
      state,
      bio: $('editClientBio').value.trim()
    };

    if(!data.full_name) return toast('Informe o nome completo.');
    if(!data.phone) return toast('Informe o telefone.');
    if(!data.street || !data.number || !data.neighborhood || !data.city) return toast('Preencha rua, número, bairro e cidade.');

    const user = await api(`/api/users/${currentUser.id}`, {
      method:'PUT',
      body: JSON.stringify(data)
    });

    currentUser = user;
    editClientPhotoData = '';
    const preview = $('editClientPhotoPreview');
    if(preview) preview.classList.add('hidden');
    safeText('editClientPhotoStatus', 'Manter foto atual');
    setLoggedUI();
    renderClientDetails();
    if($('clientEditBox')) $('clientEditBox').classList.add('hidden');
    toast('Dados do cliente atualizados.');
  }catch(err){
    toast(err.message || 'Não foi possível atualizar os dados.');
  }
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

    console.log('DADOS ENVIADOS /api/walks:', data);

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
    toast(walk.payment_status === 'pago' ? 'Pagamento confirmado automaticamente.' : 'Pagamento ainda aguardando confirmação do Mercado Pago.');
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

  const kmLive = kmBetween(
    Number(w.walker_lat || -22.5900),
    Number(w.walker_lng || -43.1810),
    Number(w.pickup_lat || -22.5884),
    Number(w.pickup_lng || -43.1847)
  );
  const eta = etaMinutesFromKm(kmLive);
  const activeLabel = ['aceito','pagamento_confirmado','em_andamento'].includes(w.status) ? 'Corrida ativa' : 'Pedido criado';

  const box = $('currentWalkBox');
  if(box){
    box.innerHTML = `<strong>#${w.id} • ${w.pet || 'Pet'}</strong><br>
    Cliente: ${w.client}<br>
    Passeador: ${w.walker}<br>
    Status: <span class="badge ${w.status}">${w.status}</span> <span class="badge aceito">${activeLabel}</span><br>
    Pagamento: <span class="badge ${w.payment_status}">${w.payment_status}</span><br>
    Distância do pedido: ${w.distance_km} km • ${w.duration_minutes} min • R$ ${Number(w.estimated_price).toFixed(2)}<br>
    Distância ao cliente: <strong>${kmLive.toFixed(2)} km</strong><br>
    Previsão de chegada: <strong>${eta} min</strong><br>
    Localização passeador: ${Number(w.walker_lat || -22.5900).toFixed(5)}, ${Number(w.walker_lng || -43.1810).toFixed(5)}`;
  }

  const pixBox = $('pixBox');
  if(pixBox){
    const copy = w.mp_qr_code || w.pix_code || '';
    let qrImg = '';
    if(w.mp_qr_code_base64){
      qrImg = `<img alt="QR Code PIX Mercado Pago" src="data:image/png;base64,${w.mp_qr_code_base64}" style="max-width:240px;width:100%;display:block;margin:10px auto;border-radius:16px;border:1px solid #e2e8f0;">`;
    }else if(copy && !copy.includes('PIX-SIMULADO')){
      qrImg = `<img alt="QR Code PIX" src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(copy)}" style="max-width:240px;width:100%;display:block;margin:10px auto;border-radius:16px;border:1px solid #e2e8f0;">`;
    }
    const ticket = w.mp_ticket_url ? `<br><a href="${escapeHtml(w.mp_ticket_url)}" target="_blank" rel="noopener">Abrir pagamento Mercado Pago</a>` : '';
    const copyText = copy || 'Aguardando geração do PIX Mercado Pago.';
    const copyButton = copy ? `<button type="button" class="ghost" style="margin-top:10px" onclick="navigator.clipboard.writeText(\`${copy.replace(/`/g, '')}\`); toast('Código PIX copiado')">Copiar código PIX</button>` : '';
    pixBox.innerHTML = `${qrImg}<div style="word-break:break-all;white-space:pre-wrap;background:#0f172a;color:#d1fae5;border-radius:16px;padding:12px;font-size:12px;line-height:1.35;">${escapeHtml(copyText)}</div>${copyButton}${ticket}`;
  }
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
      <button class="warn" type="button" onclick="payWalk(${w.id})">Verificar PIX</button>
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
    const visibleWalkers = walkers.slice(0, 6);
    $('walkerCards').innerHTML = `
      <div class="notice" style="padding:12px;margin:6px 0 10px;border-radius:16px;">
        <strong>${walkers.length}</strong> passeador(es) disponíveis. Use o campo acima para escolher.
      </div>
      <div style="display:grid;gap:8px;">
        ${visibleWalkers.map(w => `<div class="walker-card" data-walker-card="${w.id}" style="display:flex;align-items:center;gap:10px;padding:10px;border-radius:16px;">
          ${photoOrAvatar(w, '🚶')}
          <div style="flex:1;min-width:0;">
            <strong style="display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(w.full_name)}</strong>
            <small class="muted">⭐ ${Number(w.rating || 5).toFixed(1)} • ${escapeHtml(w.neighborhood || '-')}</small>
          </div>
          <button type="button" style="padding:9px 12px;border-radius:12px;" onclick="selectWalker(${w.id})">Escolher</button>
        </div>`).join('')}
      </div>`;
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

      if(data.type && data.walk && currentUser && data.walk.client_id === currentUser.id){
        window.amigoPetPWA?.notify('AmigoPet Cliente', labels[data.type] || 'Atualização do passeio', '/');
      }

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
loadPricing().catch(()=>{});
showView('home', true);
connectWS();

async function loadPricing(){
  const box = $('homePricing');
  if(!box) return;

  try{
    const prices = await api('/api/pricing');
    pricingConfig = prices;

    const price30 = Number(prices.price_30 ?? 30);
    const price45 = Number(prices.price_45 ?? 38);
    const price60 = Number(prices.price_60 ?? 46);
    const extraDog = Number(prices.extra_dog ?? 9);

    box.innerHTML = `
      <div style="display:grid;gap:10px;">
        <div class="item">
          <strong>30 minutos</strong><br>
          <span>R$ ${price30.toFixed(2)}</span>
        </div>

        <div class="item">
          <strong>45 minutos</strong><br>
          <span>R$ ${price45.toFixed(2)}</span>
        </div>

        <div class="item">
          <strong>60 minutos</strong><br>
          <span>R$ ${price60.toFixed(2)}</span>
        </div>

        <div class="item">
          <strong>Cão adicional</strong><br>
          <span>+ R$ ${extraDog.toFixed(2)}</span>
        </div>
      </div>
    `;
  }catch(e){
    console.error('Erro ao carregar preços:', e);

    box.innerHTML = `
      <div class="notice">
        Não foi possível carregar os valores agora.
        <br><br>
        Tente atualizar a página em alguns segundos.
      </div>
    `;
  }
}
