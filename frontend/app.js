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
    const pet = await api('/api/pets', {method:'POST', body: JSON.stringify({owner_id: currentUser.id, name:$('petName').value, breed:$('petBreed').value, size:$('petSize').value, age:$('petAge').value, photo:$('petPhoto').value, notes:$('petNotes').value})});
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

async function acceptWalk(id){
  try{
    const walkers = await api('/api/users?role=walker');
    const walkerId = (currentUser && currentUser.role === 'walker') ? currentUser.id : (lastWalk?.walker_id || selectedWalkerId || walkers[0]?.id || 3);
    const walk = await api(`/api/walks/${id}/accept?walker_id=${walkerId}`, {method:'POST'});
    lastWalk = walk; currentRequestId = id; renderCurrentWalk(walk);
    toast('Passeador aceitou o convite.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function rejectWalk(id){
  try{ const walk = await api(`/api/walks/${id}/reject`, {method:'POST'}); lastWalk = walk; renderCurrentWalk(walk); toast('Convite recusado.'); await refreshAll(); }
  catch(err){ toast(err.message); }
}
async function payWalk(id){
  try{ const walk = await api(`/api/walks/${id}/pay`, {method:'POST'}); lastWalk = walk; currentRequestId = id; renderCurrentWalk(walk); toast('PIX simulado confirmado.'); await refreshAll(); }
  catch(err){ toast(err.message); }
}
async function startWalk(id){
  try{ const walk = await api(`/api/walks/${id}/start`, {method:'POST'}); lastWalk = walk; renderCurrentWalk(walk); toast('Passeio iniciado.'); await refreshAll(); }
  catch(err){ toast(err.message); }
}
async function finishWalk(id){
  try{ const walk = await api(`/api/walks/${id}/finish`, {method:'POST'}); lastWalk = walk; renderCurrentWalk(walk); toast('Passeio finalizado.'); await refreshAll(); }
  catch(err){ toast(err.message); }
}
function startCurrentWalk(){ if(currentRequestId) startWalk(currentRequestId); else toast('Selecione um pedido.'); }
function finishCurrentWalk(){ if(currentRequestId) finishWalk(currentRequestId); else toast('Selecione um pedido.'); }

async function simulateMove(){
  if(!currentRequestId) return toast('Crie ou selecione um pedido primeiro.');
  moveStep = (moveStep + 1) % 5;
  const positions = [
    {left:'70%', top:'20%'}, {left:'60%', top:'30%'}, {left:'50%', top:'41%'}, {left:'38%', top:'52%'}, {left:'22%', top:'62%'}
  ];
  const p = positions[moveStep];
  $('walkerPin').style.left = p.left; $('walkerPin').style.top = p.top; $('walkerPin').style.right = 'auto';
  await api(`/api/walks/${currentRequestId}/location`, {method:'POST', body: JSON.stringify({lat:-22.5900 + moveStep/1000, lng:-43.1810 - moveStep/1000})});
}

function renderCurrentWalk(w){
  if(!w) return;
  $('currentWalkBox').innerHTML = `<strong>#${w.id} • ${w.pet || 'Pet'}</strong><br>Cliente: ${w.client}<br>Passeador: ${w.walker}<br>Status: <span class="badge ${w.status}">${w.status}</span><br>Pagamento: <span class="badge ${w.payment_status}">${w.payment_status}</span><br>Distância: ${w.distance_km} km • ${w.duration_minutes} min • R$ ${Number(w.estimated_price).toFixed(2)}`;
  $('pixBox').textContent = w.pix_code || 'PIX será gerado ao criar o pedido.';
}

function walkItem(w, withActions=true){
  const timer = w.seconds_left > 0 ? `<span class="badge convite_enviado">⏱ ${Math.floor(w.seconds_left/60)}:${String(w.seconds_left%60).padStart(2,'0')}</span>` : '';
  return `<div class="item">
    <div class="item-head">
      <div><strong>#${w.id} • ${w.pet || 'Pet não informado'}</strong><br><span class="muted">${w.client} → ${w.walker}</span><br><span>${w.address}</span></div>
      <div><span class="badge ${w.status}">${w.status}</span> <span class="badge ${w.payment_status}">${w.payment_status}</span>${timer}</div>
    </div>
    <div class="muted">${w.duration_minutes} min • ${w.dogs_count} cão(s) • ${w.distance_km} km • R$ ${Number(w.estimated_price).toFixed(2)}</div>
    ${withActions ? `<div class="actions"><button class="ok" onclick="acceptWalk(${w.id})">Aceitar</button><button class="danger" onclick="rejectWalk(${w.id})">Recusar</button><button class="warn" onclick="payWalk(${w.id})">Confirmar PIX</button><button onclick="startWalk(${w.id})">Iniciar</button><button onclick="finishWalk(${w.id})">Finalizar</button><button onclick="openChat(${w.id})">Chat</button><button onclick="currentRequestId=${w.id}; lastWalk=${JSON.stringify(w).replaceAll('"','&quot;')}; renderCurrentWalk(lastWalk); showView('tracking')">Rota</button></div>` : ''}
  </div>`;
}

async function refreshAll(){
  const [users, walkers, walks] = await Promise.all([api('/api/users'), api('/api/users?role=walker'), api('/api/walks')]);
  const clients = users.filter(u => u.role === 'client');
  $('mClients').textContent = clients.length; $('mWalkers').textContent = walkers.length; $('mWalks').textContent = walks.length;
  $('sUsers').textContent = users.length; $('sClients').textContent = clients.length; $('sWalkers').textContent = walkers.length; $('sWalks').textContent = walks.length;

  $('walkerSelect').innerHTML = `<option value="">Escolha um passeador</option>` + walkers.map(w => `<option value="${w.id}">${w.full_name} • ⭐ ${w.rating} • ${w.neighborhood}</option>`).join('');
  $('walkerCards').innerHTML = walkers.map(w => `<div class="walker-card" data-walker-card="${w.id}"><div class="avatar">🚶</div><strong>${w.full_name}</strong><span>⭐ ${w.rating} • ${w.neighborhood || '-'}</span><p class="muted">${w.bio || 'Passeador disponível.'}</p><button onclick="selectWalker(${w.id})">Escolher</button></div>`).join('');

  const ownerId = currentUser?.role === 'client' ? currentUser.id : clients[0]?.id;
  const pets = ownerId ? await api(`/api/pets?owner_id=${ownerId}`) : [];
  $('petSelect').innerHTML = `<option value="">Escolha o pet</option>` + pets.map(p => `<option value="${p.id}">${p.name} • ${p.size}</option>`).join('');

  $('walkerRequests').innerHTML = walks.length ? walks.map(w => walkItem(w)).join('') : '<div class="notice">Sem solicitações.</div>';
  $('adminWalks').innerHTML = walks.length ? walks.map(w => walkItem(w)).join('') : '<div class="notice">Nenhum pedido criado.</div>';
  $('adminUsers').innerHTML = users.map(u => `<div class="item"><strong>${u.full_name}</strong><br><span class="muted">${u.email}</span><br>Tipo: ${u.role} • Cidade: ${u.city || '-'} • ⭐ ${u.rating}</div>`).join('');
  if(!lastWalk && walks[0]){ lastWalk = walks[0]; currentRequestId = walks[0].id; renderCurrentWalk(walks[0]); }
}

function toggleChat(){ $('chatBox').classList.toggle('open'); if($('chatBox').classList.contains('open')) loadMessages(); }
async function openChat(requestId){ currentRequestId = requestId; $('chatBox').classList.add('open'); await loadMessages(); }
async function loadMessages(){
  if(!currentRequestId){ $('chatMessages').innerHTML = '<div class="notice">Abra uma solicitação primeiro.</div>'; return; }
  const msgs = await api(`/api/messages/${currentRequestId}`);
  $('chatMessages').innerHTML = msgs.length ? msgs.map(m => `<div class="bubble">${m.text}<br><small>${new Date(m.created_at).toLocaleString('pt-BR')}</small></div>`).join('') : '<div class="notice">Nenhuma mensagem ainda.</div>';
}
async function sendMessage(){
  try{
    if(!currentRequestId) return toast('Abra uma solicitação primeiro.');
    if(!currentUser) await login();
    const text = $('chatText').value.trim();
    if(!text) return;
    await api('/api/messages', {method:'POST', body: JSON.stringify({request_id: currentRequestId, sender_id: currentUser.id, text})});
    $('chatText').value = '';
    await loadMessages();
  }catch(err){ toast(err.message); }
}

connectWS();
refreshAll().catch(() => toast('Backend iniciando ou indisponível.'));
setInterval(refreshAll, 10000);
