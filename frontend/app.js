const API = '';
let currentUser = null;
let currentRequestId = null;

const $ = (id) => document.getElementById(id);

function toast(msg){
  const el = $('toast');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(()=> el.style.display = 'none', 2600);
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

async function login(){
  try{
    currentUser = await api('/api/auth/login', {
      method:'POST',
      body: JSON.stringify({email:$('loginEmail').value, password:$('loginPassword').value})
    });
    $('loggedUser').innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>${currentUser.role}</strong>`;
    toast('Login realizado com sucesso.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function createPet(){
  try{
    if(!currentUser) await login();
    const pet = await api('/api/pets', {
      method:'POST',
      body: JSON.stringify({owner_id: currentUser.id, name:$('petName').value, breed:$('petBreed').value, size:$('petSize').value, age:$('petAge').value, notes:$('petNotes').value})
    });
    toast(`Pet ${pet.name} cadastrado.`);
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function createWalk(){
  try{
    if(!currentUser) await login();
    const data = {
      client_id: currentUser.id,
      walker_id: Number($('walkerSelect').value) || null,
      pet_id: Number($('petSelect').value) || null,
      address: $('address').value,
      duration_minutes: Number($('duration').value),
      dogs_count: Number($('dogsCount').value),
      notes: 'Solicitação criada pelo cliente.'
    };
    const walk = await api('/api/walks', {method:'POST', body: JSON.stringify(data)});
    currentRequestId = walk.id;
    toast(`Solicitação #${walk.id} criada. Valor estimado R$ ${walk.estimated_price.toFixed(2)}`);
    await refreshAll();
    showView('walker');
  }catch(err){ toast(err.message); }
}

async function acceptWalk(id){
  try{
    const walkers = await api('/api/users?role=walker');
    const walkerId = (currentUser && currentUser.role === 'walker') ? currentUser.id : (walkers[0]?.id || 3);
    await api(`/api/walks/${id}/accept?walker_id=${walkerId}`, {method:'POST'});
    toast('Passeio aceito.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function rejectWalk(id){
  try{
    await api(`/api/walks/${id}/reject`, {method:'POST'});
    toast('Passeio recusado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

async function payWalk(id){
  try{
    await api(`/api/walks/${id}/pay`, {method:'POST'});
    toast('Pagamento simulado confirmado.');
    await refreshAll();
  }catch(err){ toast(err.message); }
}

function walkItem(w, withActions=true){
  return `<div class="item">
    <div class="item-head">
      <div><strong>#${w.id} • ${w.pet || 'Pet não informado'}</strong><br><span class="muted">${w.client} → ${w.walker}</span><br><span>${w.address}</span></div>
      <div><span class="badge ${w.status}">${w.status}</span> <span class="badge ${w.payment_status}">${w.payment_status}</span></div>
    </div>
    <div class="muted">${w.duration_minutes} min • ${w.dogs_count} cão(s) • R$ ${Number(w.estimated_price).toFixed(2)}</div>
    ${withActions ? `<div class="actions"><button class="ok" onclick="acceptWalk(${w.id})">Aceitar</button><button class="danger" onclick="rejectWalk(${w.id})">Recusar</button><button class="warn" onclick="payWalk(${w.id})">Confirmar pagamento</button><button onclick="openChat(${w.id})">Chat</button></div>` : ''}
  </div>`;
}

async function refreshAll(){
  const [users, walkers, walks] = await Promise.all([api('/api/users'), api('/api/users?role=walker'), api('/api/walks')]);
  const clients = users.filter(u => u.role === 'client');
  $('mClients').textContent = clients.length;
  $('mWalkers').textContent = walkers.length;
  $('mWalks').textContent = walks.length;
  $('sUsers').textContent = users.length;
  $('sClients').textContent = clients.length;
  $('sWalkers').textContent = walkers.length;
  $('sWalks').textContent = walks.length;

  $('walkerSelect').innerHTML = `<option value="">Escolha um passeador</option>` + walkers.map(w => `<option value="${w.id}">${w.full_name} • ⭐ ${w.rating}</option>`).join('');

  const ownerId = currentUser?.id || clients[0]?.id;
  const pets = ownerId ? await api(`/api/pets?owner_id=${ownerId}`) : [];
  $('petSelect').innerHTML = `<option value="">Escolha o pet</option>` + pets.map(p => `<option value="${p.id}">${p.name} • ${p.size}</option>`).join('');

  $('walkerRequests').innerHTML = walks.length ? walks.map(w => walkItem(w)).join('') : '<div class="notice">Sem solicitações para exibir.</div>';
  $('adminWalks').innerHTML = walks.length ? walks.map(w => walkItem(w)).join('') : '<div class="notice">Nenhum pedido criado.</div>';
  $('adminUsers').innerHTML = users.map(u => `<div class="item"><strong>${u.full_name}</strong><br><span class="muted">${u.email}</span><br>Tipo: ${u.role} • Cidade: ${u.city || '-'}</div>`).join('');
}

function toggleChat(){ $('chatBox').classList.toggle('open'); }
async function openChat(requestId){
  currentRequestId = requestId;
  $('chatBox').classList.add('open');
  await loadMessages();
}
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

refreshAll().catch(() => toast('Backend iniciando ou indisponível.'));
