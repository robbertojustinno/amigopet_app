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
let gpsWatchId = null;

const $ = (id) => document.getElementById(id);
const ROLE_LABELS = {client:'Cliente', walker:'Passeador', admin:'Administrador'};
const VIEW_ROLES = {
  home: ['guest','client','walker','admin'],
  request: ['client','admin'],
  walker: ['walker','admin'],
  tracking: ['client','walker','admin'],
  admin: ['admin']
};

function getRole(){ return currentUser?.role || 'guest'; }
function hasAccess(viewId){ return (VIEW_ROLES[viewId] || ['admin']).includes(getRole()); }
function requireLogin(){
  if(currentUser) return true;
  toast('Faça login para acessar esta área.');
  showView('home', true);
  return false;
}
function requireRole(roles){
  if(!requireLogin()) return false;
  if(roles.includes(currentUser.role) || currentUser.role === 'admin') return true;
  toast('Acesso bloqueado para este perfil.');
  showView('home', true);
  return false;
}
function saveSession(){ if(currentUser) localStorage.setItem('amigopet_user', JSON.stringify(currentUser)); }
function restoreSession(){ try{ const saved = localStorage.getItem('amigopet_user'); if(saved) currentUser = JSON.parse(saved); }catch(e){ currentUser = null; } }
function logout(){
  currentUser = null; currentRequestId = null; selectedWalkerId = null; lastWalk = null;
  localStorage.removeItem('amigopet_user');
  updateAuthUI(); showView('home', true); toast('Sessão encerrada.');
}
function updateAuthUI(){
  const role = getRole();
  document.querySelectorAll('.nav-btn').forEach(btn => {
    const roles = (btn.dataset.roles || '').split(',').filter(Boolean);
    if(btn.id === 'logoutBtn'){
      btn.style.display = currentUser ? 'inline-flex' : 'none';
      return;
    }
    btn.style.display = roles.length === 0 || roles.includes(role) ? 'inline-flex' : 'none';
  });
  const logged = $('loggedUser');
  if(logged){
    logged.innerHTML = currentUser
      ? `<strong>${currentUser.full_name}</strong> conectado como <strong>${ROLE_LABELS[currentUser.role] || currentUser.role}</strong>`
      : 'Nenhum usuário conectado. Faça login para liberar sua área.';
  }
}


function toast(msg){
  const el = $('toast');
  if(!el) return alert(msg);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(()=> el.style.display = 'none', 2800);
}

function safeText(id, value){
  const el = $(id);
  if(el) el.textContent = value;
}

function fillLogin(){
  $('loginEmail').value = $('quickLogin').value;
  $('loginPassword').value = '123456';
}

function showView(id, force=false){
  if(!force && !hasAccess(id)){
    toast(currentUser ? 'Seu perfil não tem acesso a esta tela.' : 'Faça login para acessar esta área.');
    id = 'home';
  }
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const view = $(id);
  if(view) view.classList.add('active');
  document.querySelectorAll(`[data-view="${id}"]`).forEach(b => b.classList.add('active'));
  refreshAll().catch(()=>{});
  if(id === 'tracking') setTimeout(()=> { initMap(); if(lastWalk) renderMap(lastWalk); }, 250);
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
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => safeText('liveStatus', 'Tempo real conectado');
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
      toast(labels[data.type] || 'Atualização recebida');
      if(data.walk){
        lastWalk = data.walk;
        currentRequestId = data.walk.id;
        renderCurrentWalk(data.walk);
        renderMap(data.walk);
      }
      await refreshAll();
      if(currentRequestId) loadMessages();
    };
    ws.onclose = () => {
      safeText('liveStatus', 'Reconectando tempo real...');
      setTimeout(connectWS, 2500);
    };
  }catch(e){
    safeText('liveStatus', 'Tempo real indisponível');
  }
}

async function login(){
  try{
    currentUser = await api('/api/auth/login', {method:'POST', body: JSON.stringify({email:$('loginEmail').value, password:$('loginPassword').value})});
    saveSession();
    updateAuthUI();
    toast('Login realizado.');
    await refreshAll();
    if(currentUser.role === 'admin') showView('admin', true);
    else if(currentUser.role === 'walker') showView('walker', true);
    else showView('request', true);
  }catch(err){ toast(err.message); }
}


async function loginWalker(){
  $('loginEmail').value = 'passeador@amigopet.com';
  $('loginPassword').value = '123456';
  await login();
}

async function createPet(){
  try{
    if(!requireRole(['client'])) return;
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
    if(!requireRole(['client'])) return;
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
    const walk = await api('/api/walks', {method:'POST', body: JSON.stringify(data)});
    currentRequestId = walk.id;
    lastWalk = walk;
    renderCurrentWalk(walk);
    renderMap(walk);
    toast(`Convite #${walk.id} enviado. R$ ${walk.estimated_price.toFixed(2)}`);
    await refreshAll();
    showView('tracking');
  }catch(err){ toast(err.message); }
}

async function acceptWalk(id){
  try{
    if(!requireRole(['walker'])) return;
    const walkers = await api('/api/users?role=walker');
    const walkerId = (currentUser && currentUser.role === 'walker') ? currentUser.id : (lastWalk?.walker_id || selectedWalkerId || walkers[0]?.id || 3);
    const walk = await api(`/api/walks/${id}/accept?walker_id=${walkerId}`, {method:'POST'});
    lastWalk = walk; currentRequestId = id; renderCurrentWalk(walk); renderMap(walk);
    toast('Passeador aceitou o convite.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function rejectWalk(id){
  try{
    if(!requireRole(['walker'])) return;
    const walk = await api(`/api/walks/${id}/reject`, {method:'POST'});
    lastWalk = walk; renderCurrentWalk(walk); renderMap(walk);
    toast('Convite recusado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function payWalk(id){
  try{
    if(!requireRole(['client','admin'])) return;
    const walk = await api(`/api/walks/${id}/pay`, {method:'POST'});
    lastWalk = walk; currentRequestId = id; renderCurrentWalk(walk); renderMap(walk);
    toast('PIX confirmado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function startWalk(id){
  try{
    if(!requireRole(['walker'])) return;
    const walk = await api(`/api/walks/${id}/start`, {method:'POST'});
    lastWalk = walk; renderCurrentWalk(walk); renderMap(walk);
    toast('Passeio iniciado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function finishWalk(id){
  try{
    if(!requireRole(['walker'])) return;
    const walk = await api(`/api/walks/${id}/finish`, {method:'POST'});
    lastWalk = walk; renderCurrentWalk(walk); renderMap(walk);
    toast('Passeio finalizado.');
    stopGps();
    await refreshAll();
  }catch(err){ toast(err.message); }
}

function startCurrentWalk(){ if(currentRequestId) startWalk(currentRequestId); else toast('Selecione um pedido.'); }
function finishCurrentWalk(){ if(currentRequestId) finishWalk(currentRequestId); else toast('Selecione um pedido.'); }

function initMap(){
  const mapEl = $('map');
  if(!mapEl) return;
  if(typeof L === 'undefined'){
    mapEl.innerHTML = '<div class="map-fallback">Mapa indisponível. Verifique a conexão com a internet.</div>';
    return;
  }
  if(map) {
    setTimeout(()=> map.invalidateSize(), 150);
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
  safeText('gpsStatus', `GPS: ${Number(w.walker_lat).toFixed(5)}, ${Number(w.walker_lng).toFixed(5)}`);
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
  setTimeout(()=> map.invalidateSize(), 150);
}

async function simulateMove(){
  if(!requireRole(['walker','admin'])) return;
  if(!currentRequestId) return toast('Crie ou selecione um pedido primeiro.');
  const target = lastWalk ? [Number(lastWalk.pickup_lat), Number(lastWalk.pickup_lng)] : [-22.5884, -43.1847];
  const start = lastWalk ? [Number(lastWalk.walker_lat), Number(lastWalk.walker_lng)] : [-22.5900, -43.1810];
  moveStep = Math.min(moveStep + 1, 8);
  const progress = moveStep / 8;
  const lat = start[0] + (target[0] - start[0]) * progress;
  const lng = start[1] + (target[1] - start[1]) * progress;
  const walk = await api(`/api/walks/${currentRequestId}/location`, {method:'POST', body: JSON.stringify({lat, lng})});
  lastWalk = walk;
  renderCurrentWalk(walk);
  renderMap(walk);
}

function startGps(){
  if(!requireRole(['walker'])) return;
  if(!currentRequestId) return toast('Abra uma solicitação primeiro.');
  if(!navigator.geolocation) return toast('GPS não suportado neste aparelho/navegador.');
  if(gpsWatchId) return toast('GPS já está ativo.');

  gpsWatchId = navigator.geolocation.watchPosition(async (pos) => {
    try{
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      const walk = await api(`/api/walks/${currentRequestId}/gps`, {method:'POST', body: JSON.stringify({lat, lng})});
      lastWalk = walk;
      renderCurrentWalk(walk);
      renderMap(walk);
      safeText('gpsStatus', `GPS real ativo: ${lat.toFixed(5)}, ${lng.toFixed(5)}`);
    }catch(err){
      toast(err.message);
    }
  }, () => {
    toast('Permita o acesso à localização para usar GPS real.');
  }, {
    enableHighAccuracy: true,
    maximumAge: 3000,
    timeout: 12000
  });

  toast('GPS real ativado.');
}

function stopGps(){
  if(gpsWatchId){
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
    safeText('gpsStatus', 'GPS real parado.');
    toast('GPS parado.');
  }
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
    Localização passeador: ${Number(w.walker_lat).toFixed(5)}, ${Number(w.walker_lng).toFixed(5)}`;
  }
  const pixBox = $('pixBox');
  if(pixBox) pixBox.textContent = w.pix_code || 'PIX será gerado ao criar o pedido.';
  renderMap(w);
}

function walkItem(w, withActions=true){
  const timer = w.seconds_left > 0 ? `<span class="badge convite_enviado">⏱ ${Math.floor(w.seconds_left/60)}:${String(w.seconds_left%60).padStart(2,'0')}</span>` : '';
  return `<div class="item">
    <div class="item-head">
      <div><strong>#${w.id} • ${w.pet || 'Pet não informado'}</strong><br><span class="muted">${w.client} → ${w.walker}</span><br><span>${w.address}</span></div>
      <div><span class="badge ${w.status}">${w.status}</span> <span class="badge ${w.payment_status}">${w.payment_status}</span>${timer}</div>
    </div>
    <div class="muted">${w.duration_minutes} min • ${w.dogs_count} cão(s) • ${w.distance_km} km • R$ ${Number(w.estimated_price).toFixed(2)}</div>
    ${withActions ? `<div class="actions">
      <button class="ok" onclick="acceptWalk(${w.id})">Aceitar</button>
      <button class="danger" onclick="rejectWalk(${w.id})">Recusar</button>
      <button class="warn" onclick="payWalk(${w.id})">Confirmar PIX</button>
      <button onclick="startWalk(${w.id})">Iniciar</button>
      <button onclick="finishWalk(${w.id})">Finalizar</button>
      <button onclick="openChat(${w.id})">Chat</button>
      <button onclick="currentRequestId=${w.id}; loadWalk(${w.id}); showView('tracking')">Mapa</button>
    </div>` : ''}
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
  updateAuthUI();
  const [users, walkers, walks] = await Promise.all([api('/api/users'), api('/api/users?role=walker'), api('/api/walks')]);
  const clients = users.filter(u => u.role === 'client');

  safeText('mClients', clients.length);
  safeText('mWalkers', walkers.length);
  safeText('mWalks', walks.length);
  safeText('sUsers', users.length);
  safeText('sClients', clients.length);
  safeText('sWalkers', walkers.length);
  safeText('sWalks', walks.length);

  if($('walkerSelect')){
    $('walkerSelect').innerHTML = `<option value="">Escolha um passeador</option>` + walkers.map(w => `<option value="${w.id}">${w.full_name} • ⭐ ${w.rating} • ${w.neighborhood}</option>`).join('');
  }

  if($('walkerCards')){
    $('walkerCards').innerHTML = walkers.map(w => `<div class="walker-card" data-walker-card="${w.id}">
      <div class="avatar">🚶</div>
      <strong>${w.full_name}</strong>
      <span>⭐ ${w.rating} • ${w.neighborhood || '-'}</span>
      <p class="muted">${w.bio || 'Passeador disponível.'}</p>
      <button onclick="selectWalker(${w.id})">Escolher</button>
    </div>`).join('');
  }

  const ownerId = currentUser?.role === 'client' ? currentUser.id : clients[0]?.id;
  const pets = ownerId ? await api(`/api/pets?owner_id=${ownerId}`) : [];
  if($('petSelect')){
    $('petSelect').innerHTML = `<option value="">Escolha o pet</option>` + pets.map(p => `<option value="${p.id}">${p.name} • ${p.size}</option>`).join('');
  }

  if($('walkerRequests')){
    if(currentUser?.role === 'walker' || currentUser?.role === 'admin'){
      const visibleWalks = currentUser.role === 'walker' ? walks.filter(w => !w.walker_id || w.walker_id === currentUser.id) : walks;
      $('walkerRequests').innerHTML = visibleWalks.length ? visibleWalks.map(w => walkItem(w, true)).join('') : '<div class="notice">Sem solicitações para este passeador.</div>';
    }else{
      $('walkerRequests').innerHTML = '<div class="notice">Faça login como passeador para ver convites.</div>';
    }
  }
  if($('adminWalks')){
    $('adminWalks').innerHTML = currentUser?.role === 'admin'
      ? (walks.length ? walks.map(w => walkItem(w)).join('') : '<div class="notice">Nenhum pedido criado.</div>')
      : '<div class="notice">Área exclusiva do administrador.</div>';
  }
  if($('adminUsers')){
    $('adminUsers').innerHTML = currentUser?.role === 'admin'
      ? users.map(u => `<div class="item"><strong>${u.full_name}</strong><br><span class="muted">${u.email}</span><br>Tipo: ${u.role} • Cidade: ${u.city || '-'} • ⭐ ${u.rating}</div>`).join('')
      : '<div class="notice">Área exclusiva do administrador.</div>';
  }

  if(!lastWalk && walks[0]){
    lastWalk = walks[0];
    currentRequestId = walks[0].id;
    renderCurrentWalk(walks[0]);
    renderMap(walks[0]);
  }
}

function toggleChat(){
  $('chatBox').classList.toggle('open');
  if($('chatBox').classList.contains('open')) loadMessages();
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
  $('chatMessages').innerHTML = msgs.length ? msgs.map(m => `<div class="bubble">${m.text}<br><small>${new Date(m.created_at).toLocaleString('pt-BR')}</small></div>`).join('') : '<div class="notice">Nenhuma mensagem ainda.</div>';
}

async function sendMessage(){
  try{
    if(!requireLogin()) return;
    if(!currentRequestId) return toast('Abra uma solicitação primeiro.');
    const text = $('chatText').value.trim();
    if(!text) return;
    await api('/api/messages', {method:'POST', body: JSON.stringify({request_id: currentRequestId, sender_id: currentUser.id, text})});
    $('chatText').value = '';
    await loadMessages();
  }catch(err){ toast(err.message); }
}

restoreSession();
updateAuthUI();
connectWS();
refreshAll().catch(() => toast('Backend iniciando ou indisponível.'));
setInterval(refreshAll, 10000);
