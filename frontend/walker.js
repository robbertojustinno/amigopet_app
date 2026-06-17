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
let walkerPhotoData = "";
let registerWalkerPhotoData = "";
let walkerCameraStream = null;
let walkerCameraTarget = "";

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
  ['btnPedidos','btnAtual','btnMapa','btnPerfil','logoutBtn'].forEach(id => {
    const el = $(id);
    if(el) el.classList.toggle('hidden', !loggedIn);
  });
  const loginBtn = $('btnLogin');
  if(loginBtn) loginBtn.classList.toggle('hidden', loggedIn);
  const chip = $('profileChip');
  if(chip) chip.classList.toggle('hidden', !loggedIn);
  if(loggedIn){
    online = currentUser.available !== false;
    $('loggedUser').innerHTML = `<strong>${currentUser.full_name}</strong> conectado como <strong>Passeador</strong>`;
    $('profileName').textContent = currentUser.full_name;
    $('profilePhoto').src = currentUser.photo || `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(currentUser.full_name)}`;
    renderWalkerDetails();
    fillProfileForm();
  }else{
    $('loggedUser').textContent = 'Nenhum passeador conectado.';
  }
}


function fillProfileForm(){
  if(!currentUser) return;
  const fields = {
    profileFullName: currentUser.full_name || '',
    profilePhone: currentUser.phone || '',
    profileDocument: currentUser.document || '',
    profileNeighborhood: currentUser.neighborhood || '',
    profileCity: currentUser.city || '',
    profileBio: currentUser.bio || ''
  };
  Object.entries(fields).forEach(([id, value]) => { if($(id)) $(id).value = value; });
  walkerPhotoData = currentUser.photo || '';
  renderProfilePreview();
}

function renderProfilePreview(){
  const box = $('profilePreview');
  if(!box) return;
  if(!currentUser){ box.textContent = 'Faça login para editar seu perfil.'; return; }
  const name = $('profileFullName')?.value || currentUser.full_name || 'Passeador';
  const phone = $('profilePhone')?.value || currentUser.phone || '-';
  const city = $('profileCity')?.value || currentUser.city || '-';
  const neighborhood = $('profileNeighborhood')?.value || currentUser.neighborhood || '-';
  const bio = $('profileBio')?.value || currentUser.bio || 'Passeador disponível.';
  const photo = walkerPhotoData || currentUser.photo || `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(name)}`;
  box.innerHTML = `
    <div class="item-head">
      <img src="${photo}" alt="Foto do passeador" style="width:64px;height:64px;border-radius:20px;object-fit:cover;border:1px solid #d8e2ee;" />
      <div>
        <strong>${name}</strong><br>
        <span class="muted">${neighborhood} • ${city}</span><br>
        <span class="badge aceito">online</span>
      </div>
    </div>
    <p>Telefone: ${phone}</p>
    <p class="muted">${bio}</p>
  `;
  const preview = $('profilePhotoPreview');
  if(preview){
    preview.innerHTML = walkerPhotoData ? `<img src="${walkerPhotoData}" alt="Prévia" style="max-width:110px;max-height:110px;border-radius:18px;object-fit:cover;" />` : 'Nenhuma foto selecionada.';
  }
}

function bindProfileForm(){
  ['profileFullName','profilePhone','profileDocument','profileNeighborhood','profileCity','profileBio'].forEach(id => {
    const el = $(id);
    if(el) el.addEventListener('input', renderProfilePreview);
  });
  const file = $('profilePhotoFile');
  if(file){
    file.addEventListener('change', () => {
      const selected = file.files && file.files[0];
      if(!selected) return;
      const reader = new FileReader();
      reader.onload = () => {
        walkerPhotoData = reader.result;
        renderProfilePreview();
      };
      reader.readAsDataURL(selected);
    });
  }
}

async function saveWalkerProfile(){
  try{
    if(!requireWalker()) return;
    const payload = {
      full_name: $('profileFullName').value.trim(),
      phone: $('profilePhone').value.trim(),
      document: $('profileDocument').value.trim(),
      neighborhood: $('profileNeighborhood').value.trim(),
      city: $('profileCity').value.trim(),
      bio: $('profileBio').value.trim(),
      photo: walkerPhotoData || currentUser.photo || ''
    };
    if(!payload.full_name) throw new Error('Informe o nome do passeador.');
    currentUser = await api(`/api/walkers/${currentUser.id}/profile`, {method:'PUT', body: JSON.stringify(payload)});
    localStorage.setItem('amigopet_walker_user', JSON.stringify(currentUser));
    setLoggedUI();
    toast('Perfil do passeador atualizado.');
  }catch(err){ toast(err.message); }
}


function toggleWalkerRegister(){
  const box = $('registerWalkerBox');
  if(!box) return toast('Formulário de cadastro não encontrado.');
  box.classList.toggle('hidden');
  if(!box.classList.contains('hidden')){
    box.scrollIntoView({behavior:'smooth', block:'start'});
  }
}

async function handleRegisterWalkerPhoto(event){
  const file = event.target.files?.[0];
  if(!file) return;

  if(file.size > 1_500_000){
    event.target.value = '';
    return toast('Use uma imagem menor que 1,5 MB.');
  }

  const reader = new FileReader();
  reader.onload = () => {
    registerWalkerPhotoData = reader.result;
    const preview = $('registerWalkerPhotoPreview');
    if(preview){
      preview.innerHTML = `<img src="${registerWalkerPhotoData}" alt="Prévia" style="max-width:110px;max-height:110px;border-radius:18px;object-fit:cover;" />`;
    }
  };
  reader.readAsDataURL(file);
}

async function registerWalker(){
  try{
    const data = {
      full_name: $('registerWalkerName').value.trim(),
      email: $('registerWalkerEmail').value.trim(),
      password: $('registerWalkerPassword').value.trim(),
      role: 'walker',
      phone: $('registerWalkerPhone').value.trim(),
      photo: registerWalkerPhotoData,
      document: $('registerWalkerDocument').value.trim(),
      neighborhood: $('registerWalkerNeighborhood').value.trim(),
      city: $('registerWalkerCity').value.trim(),
      bio: $('registerWalkerBio').value.trim()
    };

    const required = [
      ['full_name','nome completo'],
      ['email','e-mail'],
      ['password','senha'],
      ['phone','telefone'],
      ['photo','foto do passeador'],
      ['document','documento'],
      ['neighborhood','bairro'],
      ['city','cidade']
    ];

    for(const [key,label] of required){
      if(!data[key]) return toast(`Preencha: ${label}.`);
    }

    if(data.password.length < 6) return toast('A senha deve ter no mínimo 6 caracteres.');

    const user = await api('/api/auth/register', {
      method:'POST',
      body: JSON.stringify(data)
    });

    currentUser = user;
    localStorage.setItem('amigopet_walker_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    showView('perfil', true);
    toast('Conta de passeador criada com sucesso.');
  }catch(err){
    toast(err.message || 'Não foi possível criar a conta de passeador.');
  }
}



function toggleWalkerForgotPassword(){
  const box = $('forgotWalkerPasswordBox');
  if(!box) return;
  const email = $('loginEmail')?.value?.trim() || '';
  if($('forgotWalkerEmail')) $('forgotWalkerEmail').value = email;
  box.classList.toggle('hidden');
}

async function requestWalkerPasswordReset(){
  try{
    const email = $('forgotWalkerEmail').value.trim();
    if(!email) return toast('Informe o e-mail cadastrado.');

    const result = await api('/api/auth/request-password-reset', {
      method:'POST',
      body: JSON.stringify({email})
    });
    toast(result.message || 'Código de recuperação enviado por e-mail.');
  }catch(err){
    toast(err.message || 'Não foi possível gerar o código.');
  }
}

async function confirmWalkerPasswordReset(){
  try{
    const email = $('forgotWalkerEmail').value.trim();
    const code = $('resetWalkerCode').value.trim();
    const new_password = $('resetWalkerNewPassword').value.trim();

    if(!email || !code || !new_password) return toast('Preencha e-mail, código e nova senha.');
    if(new_password.length < 6) return toast('A nova senha deve ter no mínimo 6 caracteres.');

    const result = await api('/api/auth/reset-password', {
      method:'POST',
      body: JSON.stringify({email, code, new_password})
    });

    $('loginEmail').value = email;
    $('loginPassword').value = '';
    $('resetWalkerCode').value = '';
    $('resetWalkerNewPassword').value = '';

    const box = $('forgotWalkerPasswordBox');
    if(box) box.classList.add('hidden');

    toast(result.message || 'Senha alterada com sucesso.');
  }catch(err){
    toast(err.message || 'Não foi possível alterar a senha.');
  }
}



function toggleWalkerRegister(){
  const box = $('registerWalkerBox');
  if(!box) return toast('Formulário de cadastro não encontrado.');
  box.classList.toggle('hidden');
  if(!box.classList.contains('hidden')){
    box.scrollIntoView({behavior:'smooth', block:'start'});
  }
}

async function handleRegisterWalkerPhoto(event){
  const file = event.target.files?.[0];
  if(!file) return;

  if(file.size > 1_500_000){
    event.target.value = '';
    return toast('Use uma imagem menor que 1,5 MB.');
  }

  const reader = new FileReader();
  reader.onload = () => {
    registerWalkerPhotoData = reader.result;
    const preview = $('registerWalkerPhotoPreview');
    if(preview){
      preview.innerHTML = `<img src="${registerWalkerPhotoData}" alt="Prévia" style="max-width:110px;max-height:110px;border-radius:18px;object-fit:cover;" />`;
    }
  };
  reader.readAsDataURL(file);
}

async function registerWalker(){
  try{
    const data = {
      full_name: $('registerWalkerName').value.trim(),
      email: $('registerWalkerEmail').value.trim(),
      password: $('registerWalkerPassword').value.trim(),
      role: 'walker',
      phone: $('registerWalkerPhone').value.trim(),
      photo: registerWalkerPhotoData,
      document: $('registerWalkerDocument').value.trim(),
      neighborhood: $('registerWalkerNeighborhood').value.trim(),
      city: $('registerWalkerCity').value.trim(),
      bio: $('registerWalkerBio').value.trim()
    };

    const required = [
      ['full_name','nome completo'],
      ['email','e-mail'],
      ['password','senha'],
      ['phone','telefone'],
      ['photo','foto do passeador'],
      ['document','documento'],
      ['neighborhood','bairro'],
      ['city','cidade']
    ];

    for(const [key,label] of required){
      if(!data[key]) return toast(`Preencha: ${label}.`);
    }

    if(data.password.length < 6) return toast('A senha deve ter no mínimo 6 caracteres.');

    const user = await api('/api/auth/register', {
      method:'POST',
      body: JSON.stringify(data)
    });

    currentUser = user;
    localStorage.setItem('amigopet_walker_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    showView('perfil', true);
    toast('Conta de passeador criada com sucesso.');
  }catch(err){
    toast(err.message || 'Não foi possível criar a conta de passeador.');
  }
}

async function openWalkerCameraCapture(target){
  try{
    walkerCameraTarget = target;
    const modal = $('walkerCameraModal');
    const video = $('walkerCameraVideo');
    const title = $('walkerCameraTitle');

    if(!modal || !video) return toast('Câmera não disponível nesta tela.');

    if(title){
      title.textContent = target === 'profile' ? 'Tirar nova foto do perfil' : 'Tirar foto do cadastro';
    }

    walkerCameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user' },
      audio: false
    });

    video.srcObject = walkerCameraStream;
    modal.classList.add('open');
  }catch(err){
    toast('Não foi possível abrir a câmera. Verifique a permissão do navegador.');
  }
}

function closeWalkerCameraCapture(){
  const modal = $('walkerCameraModal');
  const video = $('walkerCameraVideo');

  if(walkerCameraStream){
    walkerCameraStream.getTracks().forEach(track => track.stop());
  }

  walkerCameraStream = null;
  walkerCameraTarget = "";

  if(video) video.srcObject = null;
  if(modal) modal.classList.remove('open');
}

function takeWalkerCameraPhoto(){
  const video = $('walkerCameraVideo');
  const canvas = $('walkerCameraCanvas');

  if(!video || !canvas || !walkerCameraTarget) return toast('Câmera não iniciada.');

  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;

  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, width, height);

  const dataUrl = canvas.toDataURL('image/jpeg', 0.82);

  if(walkerCameraTarget === 'register'){
    registerWalkerPhotoData = dataUrl;
    const preview = $('registerWalkerPhotoPreview');
    if(preview){
      preview.innerHTML = `<img src="${dataUrl}" alt="Prévia" style="max-width:110px;max-height:110px;border-radius:18px;object-fit:cover;" />`;
    }
  }

  if(walkerCameraTarget === 'profile'){
    walkerPhotoData = dataUrl;
    renderProfilePreview();
  }

  closeWalkerCameraCapture();
  toast('Foto capturada com sucesso.');
}


async function login(){
  try{
    const email = $('loginEmail').value.trim();
    const password = $('loginPassword').value.trim();

    if(!email || !password) return toast('Preencha e-mail e senha.');

    const user = await api('/api/auth/login', {method:'POST', body: JSON.stringify({email, password})});

    if(user.role !== 'walker') throw new Error('Esta área é exclusiva para passeadores.');

    currentUser = user;
    localStorage.setItem('amigopet_walker_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    showView('pedidos', true);
    toast('Passeador conectado.');
  }catch(err){
    toast(err.message || 'Não foi possível entrar.');
  }
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

async function setOnline(value){
  try{
    if(!requireWalker()) return;
    const user = await api(`/api/walkers/${currentUser.id}/availability`, {
      method:'PUT',
      body: JSON.stringify({available: !!value})
    });
    currentUser = user;
    online = !!user.available;
    localStorage.setItem('amigopet_walker_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    toast(online ? 'Você está online para receber convites.' : 'Você está offline. Clientes não verão você como disponível.');
  }catch(err){
    toast(err.message || 'Não foi possível atualizar seu status.');
  }
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

function canAcceptPaid(w){
  return isAvailable(w) && String(w.payment_status || '').toLowerCase() === 'pago';
}

function walkCard(w, mode='available'){
  const canAccept = mode === 'available' && canAcceptPaid(w);
  const canReject = mode === 'available' && ['convite_enviado','pendente','pagamento_confirmado'].includes(w.status) && String(w.payment_status || '').toLowerCase() !== 'pago';
  const waitingPayment = mode === 'available' && !canAccept;
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
      ${waitingPayment ? `<div class="notice" style="padding:10px;margin:10px 0;border-radius:14px;">Aguardando pagamento PIX confirmado. O botão Aceitar só aparece depois do Mercado Pago confirmar.</div>` : ''}
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
    const selected = availableWalks.find(w => w.id === id) || currentWalk;
    if(selected && selected.payment_status !== 'pago') return toast('Aguardando pagamento PIX confirmado pelo Asaas.');
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
    if(currentWalk.payment_status !== 'pago') return toast('Pagamento PIX ainda não confirmado pelo Asaas.');
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


function ensureCurrentWalkForChat(){
  if(currentWalk && currentWalk.id) return currentWalk.id;
  const selected = availableWalks.find(w => w.walker_id === currentUser?.id && ['aceito','em_andamento','pagamento_confirmado'].includes(w.status));
  if(selected){
    currentWalk = selected;
    return selected.id;
  }
  return null;
}

function toggleWalkerChat(){
  const box = $('walkerChatBox');
  if(!box) return;
  box.classList.toggle('open');
  if(box.classList.contains('open')) loadWalkerMessages();
}

function openWalkerChat(){
  const requestId = ensureCurrentWalkForChat();
  if(!requestId) return toast('Abra ou aceite um passeio antes de usar o chat.');
  const box = $('walkerChatBox');
  if(box) box.classList.add('open');
  loadWalkerMessages();
}

async function loadWalkerMessages(){
  try{
    const requestId = ensureCurrentWalkForChat();
    const box = $('walkerChatMessages');
    if(!box) return;
    if(!requestId){
      box.innerHTML = '<div class="notice">Aceite um passeio para conversar com o cliente.</div>';
      return;
    }
    const msgs = await api(`/api/messages/${requestId}`);
    box.innerHTML = msgs.length
      ? msgs.map(m => `<div class="bubble">${escapeText(m.text)}<br><small>${new Date(m.created_at).toLocaleString('pt-BR')}</small></div>`).join('')
      : '<div class="notice">Nenhuma mensagem ainda.</div>';
    box.scrollTop = box.scrollHeight;
  }catch(err){
    toast(err.message || 'Não foi possível carregar o chat.');
  }
}

async function sendWalkerMessage(){
  try{
    if(!requireWalker()) return;
    const requestId = ensureCurrentWalkForChat();
    if(!requestId) return toast('Aceite um passeio para enviar mensagem.');
    const input = $('walkerChatText');
    const text = (input?.value || '').trim();
    if(!text) return;

    await api('/api/messages', {
      method:'POST',
      body: JSON.stringify({request_id: requestId, sender_id: currentUser.id, text})
    });

    if(input) input.value = '';
    await loadWalkerMessages();
  }catch(err){
    toast(err.message || 'Não foi possível enviar a mensagem.');
  }
}

function escapeText(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
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
      if(data.type === 'message'){
        const msg = data.message;
        if(msg && currentWalk && Number(msg.request_id) === Number(currentWalk.id)){
          toast('Nova mensagem do cliente.');
          const box = $('walkerChatBox');
          if(box && !box.classList.contains('open')) box.classList.add('open');
          await loadWalkerMessages();
        }
      }
      if(data.type === 'walker_availability_changed' && data.walker && currentUser && Number(data.walker.id) === Number(currentUser.id)){
        currentUser = data.walker;
        online = currentUser.available !== false;
        localStorage.setItem('amigopet_walker_user', JSON.stringify(currentUser));
        setLoggedUI();
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

bindProfileForm();
restoreSession();
connectWS();


window.setOnline = setOnline;
window.openWalkerChat = openWalkerChat;
window.toggleWalkerChat = toggleWalkerChat;
window.sendWalkerMessage = sendWalkerMessage;
