const API = 'https://amigopet-6td8.onrender.com';
const WS_URL = 'wss://amigopet-6td8.onrender.com/ws';

let currentUser = null;
let availableWalks = [];
let currentWalk = null;
let map = null;
let pickupMarker = null;
let walkerMarker = null;
let routeLine = null;
let moveStep = 0;
let online = true;
let gpsWatchId = null;
let gpsActive = false;
let lastGpsSentAt = 0;

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

function toast(msg){
  const el = $('toast');
  if(!el) return alert(msg);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3300);
}

async function api(path, options={}){
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });

  let data = null;
  try{ data = await res.json(); }catch(e){ data = {}; }

  if(!res.ok){
    console.error('ERRO API PASSEADOR:', path, data);
    let detail = 'Erro na requisição';
    if(Array.isArray(data?.detail)) detail = data.detail.map(e => e.msg).join(' | ');
    else if(typeof data?.detail === 'string') detail = data.detail;
    else detail = JSON.stringify(data);
    throw new Error(detail);
  }
  return data;
}

function fillWalkerDemo(){
  $('loginEmail').value = 'passeador@amigopet.com';
  $('loginPassword').value = '123456';
}

function showView(id, force=false){
  if(!force && id !== 'login' && !requireWalker()) return;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const view = $(id);
  if(view) view.classList.add('active');
  document.querySelectorAll('.nav-btn[data-view]').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector(`[data-view="${id}"]`);
  if(btn) btn.classList.add('active');
  if(id === 'mapa') setTimeout(() => { initMap(); renderMap(); }, 250);
}

document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => showView(btn.dataset.view));
});

function requireWalker(){
  if(currentUser && currentUser.role === 'walker') return true;
  toast('Faça login como passeador.');
  showView('login', true);
  return false;
}

function setLoggedUI(){
  const loggedIn = currentUser && currentUser.role === 'walker';
  ['btnPedidos','btnAtual','btnMapa','logoutBtn'].forEach(id => {
    const el = $(id);
    if(el) el.classList.toggle('hidden', !loggedIn);
  });
  const chip = $('profileChip');
  if(chip) chip.classList.toggle('hidden', !loggedIn);
  if(loggedIn){
    $('loggedUser').innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>Passeador</strong>`;
    $('profileName').textContent = currentUser.full_name;
    $('profilePhoto').src = currentUser.photo || `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(currentUser.full_name)}`;
    renderWalkerDetails();
  }else{
    $('loggedUser').textContent = 'Nenhum passeador conectado.';
  }
}

async function login(){
  try{
    const email = $('loginEmail').value.trim();
    const password = $('loginPassword').value;
    const user = await api('/api/auth/login', {method:'POST', body: JSON.stringify({email, password})});
    if(user.role !== 'walker') throw new Error('Esta área é exclusiva para passeadores.');
    currentUser = user;
    localStorage.setItem('amigopet_walker_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    showView('pedidos', true);
    toast('Passeador conectado.');
  }catch(err){ toast(err.message); }
}

function logout(){
  stopGpsTracking(false);
  currentUser = null;
  currentWalk = null;
  availableWalks = [];
  localStorage.removeItem('amigopet_walker_user');
  setLoggedUI();
  renderAvailableWalks();
  renderCurrentWalk();
  showView('login', true);
  toast('Sessão encerrada.');
}

function setOnline(value){
  online = value;
  renderWalkerDetails();
  toast(value ? 'Você está online para receber convites.' : 'Você está offline.');
}

function renderWalkerDetails(){
  if(!currentUser){
    $('walkerDetails').textContent = 'Offline';
    return;
  }
  $('onlineLabel').textContent = online ? 'Disponível' : 'Offline';
  $('walkerDetails').innerHTML = `
    <strong>${currentUser.full_name}</strong><br>
    E-mail: ${currentUser.email}<br>
    Cidade: ${currentUser.city || '-'}<br>
    Bairro: ${currentUser.neighborhood || '-'}<br>
    Avaliação: ⭐ ${Number(currentUser.rating || 5).toFixed(1)}<br>
    Status: <span class="badge ${online ? 'aceito' : 'recusado'}">${online ? 'online' : 'offline'}</span>
  `;
}

function isAvailable(w){
  return ['convite_enviado','pendente','pagamento_confirmado'].includes(w.status) && (!w.walker_id || w.walker_id === currentUser?.id);
}

function walkCard(w, mode='available'){
  const canAccept = mode === 'available' && isAvailable(w);
  const canReject = mode === 'available' && ['convite_enviado','pendente'].includes(w.status);
  return `
    <div class="item">
      <div class="item-head">
        <div>
          <strong>#${w.id} • ${w.pet || 'Pet'}</strong><br>
          <span class="muted">Cliente: ${w.client || '-'}</span><br>
          <span class="muted">Endereço: ${w.address || '-'}</span>
        </div>
        <div>
          <span class="badge ${w.status}">${w.status}</span>
          <span class="badge ${w.payment_status}">${w.payment_status || 'aguardando'}</span>
        </div>
      </div>
      <p>Distância: ${w.distance_km || 0} km • ${w.duration_minutes || 30} min • R$ ${Number(w.estimated_price || 0).toFixed(2)}</p>
      <p class="muted">Local cliente: ${Number(w.pickup_lat || 0).toFixed(5)}, ${Number(w.pickup_lng || 0).toFixed(5)}</p>
      <div class="actions">
        ${canAccept ? `<button type="button" onclick="acceptWalk(${w.id})">Aceitar</button>` : ''}
        ${canReject ? `<button class="ghost" type="button" onclick="rejectWalk(${w.id})">Recusar</button>` : ''}
        <button class="secondary" type="button" onclick="selectWalk(${w.id})">Ver detalhes</button>
      </div>
    </div>
  `;
}

function renderAvailableWalks(){
  const box = $('availableWalks');
  if(!box) return;
  if(!currentUser){ box.innerHTML = 'Faça login como passeador.'; return; }
  const list = availableWalks.filter(isAvailable);
  box.classList.toggle('notice', list.length === 0);
  box.innerHTML = list.length ? list.map(w => walkCard(w)).join('') : 'Nenhum convite disponível agora.';
}

function renderCurrentWalk(){
  const box = $('currentWalk');
  if(!box) return;
  if(!currentWalk){
    box.className = 'notice';
    box.innerHTML = 'Nenhum passeio aceito ainda.';
  }else{
    box.className = '';
    box.innerHTML = walkCard(currentWalk, 'current');
  }
  const summary = $('mapSummary');
  if(summary){
    if(currentWalk){
      const km = kmBetween(
        Number(currentWalk.walker_lat || -22.5900),
        Number(currentWalk.walker_lng || -43.1810),
        Number(currentWalk.pickup_lat || -22.5884),
        Number(currentWalk.pickup_lng || -43.1847)
      );
      summary.innerHTML = `
        <strong>#${currentWalk.id} • ${currentWalk.pet || 'Pet'}</strong><br>
        Cliente: ${currentWalk.client || '-'}<br>
        Status: <span class="badge ${currentWalk.status}">${currentWalk.status}</span><br>
        Pagamento: <span class="badge ${currentWalk.payment_status}">${currentWalk.payment_status || 'aguardando'}</span><br>
        Endereço: ${currentWalk.address || '-'}<br>
        Passeador: ${Number(currentWalk.walker_lat || 0).toFixed(5)}, ${Number(currentWalk.walker_lng || 0).toFixed(5)}<br>
        Distância até cliente: <strong>${km.toFixed(2)} km</strong><br>
        Previsão: <strong>${etaMinutesFromKm(km)} min</strong><br>
        GPS automático: <span class="badge ${gpsActive ? 'aceito' : 'recusado'}">${gpsActive ? 'ativo' : 'parado'}</span>
      `;
    }else{
      summary.innerHTML = 'Nenhum passeio selecionado.';
    }
  }
  renderMap();
}

async function refreshAll(){
  if(!currentUser) return;
  try{
    const walks = await api('/api/walks');
    availableWalks = walks;
    const activeStatuses = ['aceito','pagamento_confirmado','em_andamento'];
    currentWalk = walks.find(w => w.walker_id === currentUser.id && activeStatuses.includes(w.status)) || currentWalk;
    renderAvailableWalks();
    renderCurrentWalk();
  }catch(err){ toast(err.message); }
}

function selectWalk(id){
  const walk = availableWalks.find(w => w.id === id);
  if(walk){
    currentWalk = walk;
    renderCurrentWalk();
    showView('atual');
  }
}

async function acceptWalk(id){
  try{
    if(!requireWalker()) return;
    const walk = await api(`/api/walks/${id}/accept?walker_id=${currentUser.id}`, {method:'POST'});
    currentWalk = walk;
    await refreshAll();
    showView('atual');
    toast('Convite aceito.');
  }catch(err){ toast(err.message); }
}

async function rejectWalk(id){
  try{
    await api(`/api/walks/${id}/reject`, {method:'POST'});
    await refreshAll();
    toast('Convite recusado.');
  }catch(err){ toast(err.message); }
}

async function startCurrentWalk(){
  try{
    if(!currentWalk) return toast('Selecione ou aceite um passeio primeiro.');
    currentWalk = await api(`/api/walks/${currentWalk.id}/start`, {method:'POST'});
    renderCurrentWalk();
    startGpsTracking();
    showView('mapa');
    toast('Passeio iniciado. GPS automático ativado.');
  }catch(err){ toast(err.message); }
}

async function finishCurrentWalk(){
  try{
    if(!currentWalk) return toast('Nenhum passeio atual.');
    stopGpsTracking(false);
    currentWalk = await api(`/api/walks/${currentWalk.id}/finish`, {method:'POST'});
    renderCurrentWalk();
    toast('Passeio finalizado. GPS automático desligado.');
  }catch(err){ toast(err.message); }
}

async function sendLocation(lat, lng){
  if(!currentWalk) return toast('Nenhum passeio atual.');
  currentWalk = await api(`/api/walks/${currentWalk.id}/location`, {
    method:'POST',
    body: JSON.stringify({lat, lng})
  });
  renderCurrentWalk();
}

function startGpsTracking(){
  if(!currentWalk) return toast('Aceite ou selecione um passeio primeiro.');
  if(!navigator.geolocation) return toast('GPS não disponível neste dispositivo. Use Enviar localização ou Simular movimento.');
  if(gpsWatchId !== null) return toast('GPS automático já está ativo.');

  gpsActive = true;
  renderCurrentWalk();
  toast('GPS automático ativado. Mantenha esta tela aberta.');

  gpsWatchId = navigator.geolocation.watchPosition(
    async (pos) => {
      try{
        const now = Date.now();
        if(now - lastGpsSentAt < 4500) return;
        lastGpsSentAt = now;
        await sendLocation(pos.coords.latitude, pos.coords.longitude);
      }catch(err){
        toast(err.message || 'Falha ao enviar GPS.');
      }
    },
    (err) => {
      gpsActive = false;
      renderCurrentWalk();
      toast(err?.message || 'Permissão de localização negada.');
    },
    {enableHighAccuracy:true, timeout:12000, maximumAge:3000}
  );
}

function stopGpsTracking(showToast=true){
  if(gpsWatchId !== null && navigator.geolocation){
    navigator.geolocation.clearWatch(gpsWatchId);
  }
  gpsWatchId = null;
  gpsActive = false;
  renderCurrentWalk();
  if(showToast) toast('GPS automático desligado.');
}

function sendMyLocation(){
  if(!navigator.geolocation){
    return simulateMove();
  }
  navigator.geolocation.getCurrentPosition(
    async pos => {
      try{
        await sendLocation(pos.coords.latitude, pos.coords.longitude);
        toast('Localização enviada.');
      }catch(err){ toast(err.message); }
    },
    () => simulateMove(),
    {enableHighAccuracy:true, timeout:7000, maximumAge:5000}
  );
}

async function simulateMove(){
  try{
    if(!currentWalk) return toast('Nenhum passeio atual.');
    moveStep += 1;
    const baseLat = Number(currentWalk.pickup_lat || -22.5884);
    const baseLng = Number(currentWalk.pickup_lng || -43.1847);
    const lat = baseLat + 0.0018 - (moveStep * 0.00018);
    const lng = baseLng + 0.0018 - (moveStep * 0.00018);
    await sendLocation(lat, lng);
    toast('Movimento simulado enviado.');
  }catch(err){ toast(err.message); }
}

function initMap(){
  if(map || !window.L || !$('map')) return;
  map = L.map('map').setView([-22.5884, -43.1847], 15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(map);
}

function renderMap(){
  if(!map || !currentWalk || !window.L) return;
  const pickup = [Number(currentWalk.pickup_lat || -22.5884), Number(currentWalk.pickup_lng || -43.1847)];
  const walker = [Number(currentWalk.walker_lat || -22.5900), Number(currentWalk.walker_lng || -43.1810)];
  if(!pickupMarker) pickupMarker = L.marker(pickup).addTo(map).bindPopup('Cliente');
  else pickupMarker.setLatLng(pickup);
  if(!walkerMarker) walkerMarker = L.marker(walker).addTo(map).bindPopup('Passeador');
  else walkerMarker.setLatLng(walker);
  if(routeLine) routeLine.remove();
  routeLine = L.polyline([walker, pickup]).addTo(map);
  map.fitBounds([walker, pickup], {padding:[35,35]});
}

function connectWS(){
  try{
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => toast('Tempo real conectado.');
    ws.onmessage = async (ev) => {
      const data = JSON.parse(ev.data);
      if(data.type === 'walk_created'){
        toast('Novo convite recebido.');
        window.amigoPetPWA?.notify('AmigoPet Passeador', 'Novo convite de passeio recebido.', '/passeador');
      }
      if(data.walk){
        const w = data.walk;
        const idx = availableWalks.findIndex(item => item.id === w.id);
        if(idx >= 0) availableWalks[idx] = w;
        else availableWalks.unshift(w);
        if(currentUser && w.walker_id === currentUser.id) currentWalk = w;
        renderAvailableWalks();
        renderCurrentWalk();
      }
      if(currentUser) await refreshAll();
    };
    ws.onclose = () => setTimeout(connectWS, 2500);
  }catch(e){}
}

function restoreSession(){
  try{
    const saved = localStorage.getItem('amigopet_walker_user');
    if(saved){
      currentUser = JSON.parse(saved);
      setLoggedUI();
      refreshAll();
      showView('pedidos', true);
    }else{
      setLoggedUI();
      showView('login', true);
    }
  }catch(e){
    localStorage.removeItem('amigopet_walker_user');
    setLoggedUI();
  }
}

restoreSession();
connectWS();
