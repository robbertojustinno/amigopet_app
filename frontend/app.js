const AMIGOPET_CONFIG = window.AMIGOPET_CONFIG || {};
const AMIGOPET_ORIGIN = window.location.protocol === 'file:' || window.location.origin === 'null'
  ? 'http://localhost:8000'
  : window.location.origin;
const API = (AMIGOPET_CONFIG.API_BASE_URL || AMIGOPET_CONFIG.apiBaseUrl || AMIGOPET_ORIGIN).replace(/\/$/, '');
const WS_URL = AMIGOPET_CONFIG.WS_URL || AMIGOPET_CONFIG.wsUrl || `${API.replace(/^http/i, 'ws')}/ws`;

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
let chatSocket = null;
let chatTypingTimer = null;
let chatTypingClearTimer = null;
let creatingWalk = false;
let restoringClientSession = false;
const CLIENT_TERMS_VERSION = '1.0';
let clientTermsReadComplete = false;

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

function sanitizeHtml(html){
  const template = document.createElement('template');
  template.innerHTML = String(html ?? '');
  template.content.querySelectorAll('script, iframe, object, embed, meta, link').forEach(el => el.remove());
  template.content.querySelectorAll('*').forEach(el => {
    [...el.attributes].forEach(attr => {
      const name = attr.name.toLowerCase();
      const value = String(attr.value || '').trim();
      if(name.startsWith('on') && !isAllowedInlineHandler(name, value)){
        el.removeAttribute(attr.name);
        return;
      }
      if((name === 'href' || name === 'src' || name === 'xlink:href') && /^\s*javascript:/i.test(value)){
        el.removeAttribute(attr.name);
        return;
      }
      if(name === 'src' && /^\s*data:/i.test(value) && !/^data:image\//i.test(value)){
        el.removeAttribute(attr.name);
      }
    });
  });
  return template.innerHTML;
}

function isAllowedInlineHandler(name, value){
  if(name === 'onerror'){
    return /^this\.onerror=null;this\.src='https:\/\/api\.dicebear\.com\/8\.x\/initials\/svg\?seed=[^']*'$/.test(value);
  }
  if(name !== 'onclick') return false;
  return [
    /^navigator\.clipboard\.writeText\(`[^`]*`\); toast\('Código PIX copiado'\)$/,
    /^payWalk\(\d+\)$/,
    /^sendClientRating\(\d+, \d+\)$/,
    /^openChat\(\d+\)$/,
    /^currentRequestId=\d+; loadWalk\(\d+\); showView\('tracking', true\)$/,
    /^selectWalker\(\d+\)$/,
    /^sendWalkerRating\(\d+, \d+\)$/,
    /^acceptWalk\(\d+\)$/,
    /^rejectWalk\(\d+\)$/,
    /^openWalkerChat\(\d+\)$/,
    /^selectWalk\(\d+\)$/,
  ].some(pattern => pattern.test(value));
}

function setSafeHTML(el, html){
  if(el) el.innerHTML = sanitizeHtml(html);
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

function setInviteStatus(message, isError=false){
  const el = $('inviteStatus');
  if(!el) return;
  el.textContent = message || '';
  el.style.display = message ? 'block' : 'none';
  el.style.color = isError ? '#92400e' : '';
}

function isCsrfError(err){
  const text = String(err?.message || err || '').toLowerCase();
  return err?.status === 403 && text.includes('csrf');
}

function friendlyWalkSubmitError(error){
  const text = String(error?.message || error || '');
  const lower = text.toLowerCase();
  if(error?.status === 401 || lower.includes('autentica') || lower.includes('sessão') || lower.includes('sessao') || lower.includes('401')){
    return 'Sessão expirada. Faça login novamente e tente enviar o convite.';
  }
  if(isCsrfError(error)) return 'Não foi possível validar a segurança da requisição. Atualize a página e tente novamente.';
  if(lower.includes('pet')){
    return 'Não foi possível validar o pet selecionado. Escolha o pet novamente.';
  }
  if(lower.includes('passeador')){
    return 'Não foi possível validar o passeador selecionado. Escolha o passeador novamente.';
  }
  if(lower.includes('rate') || lower.includes('429')){
    return 'Muitas tentativas em pouco tempo. Aguarde um minuto e tente novamente.';
  }
  return text || 'Não foi possível enviar o convite. Tente novamente.';
}

function digitsOnly(value){
  return String(value || '').replace(/\D/g, '');
}

function selectedPaymentMethod(){
  return String($('paymentMethod')?.value || 'PIX').toUpperCase() === 'CREDIT_CARD' ? 'CREDIT_CARD' : 'PIX';
}

function toggleCreditCardFields(){
  const isCard = selectedPaymentMethod() === 'CREDIT_CARD';
  const box = $('creditCardBox');
  if(box) box.style.display = isCard ? 'block' : 'none';
}

function collectCreditCardData(){
  return {
    holder_name: String($('cardHolderName')?.value || '').trim(),
    number: digitsOnly($('cardNumber')?.value),
    expiry_month: digitsOnly($('cardExpiryMonth')?.value),
    expiry_year: digitsOnly($('cardExpiryYear')?.value),
    ccv: digitsOnly($('cardCcv')?.value),
    cpf_cnpj: digitsOnly($('cardCpfCnpj')?.value || currentUser?.document || ''),
    postal_code: digitsOnly($('cardPostalCode')?.value || currentUser?.zip_code || ''),
    address_number: String($('cardAddressNumber')?.value || currentUser?.number || '').trim(),
    phone: digitsOnly($('cardPhone')?.value || currentUser?.phone || '')
  };
}

function validateCreditCardData(card){
  if(!card.holder_name) return 'Informe o nome impresso no cartão.';
  if(card.number.length < 13) return 'Informe um número de cartão válido.';
  if(card.expiry_month.length !== 2) return 'Informe o mês de vencimento do cartão.';
  if(!['01','02','03','04','05','06','07','08','09','10','11','12'].includes(card.expiry_month)) return 'Informe um mês de vencimento válido.';
  if(![2, 4].includes(card.expiry_year.length)) return 'Informe o ano de vencimento do cartão.';
  if(card.ccv.length < 3) return 'Informe o CVV do cartão.';
  if(![11, 14].includes(card.cpf_cnpj.length)) return 'Informe o CPF/CNPJ do titular do cartão.';
  if(card.postal_code.length < 8) return 'Informe o CEP do titular do cartão.';
  if(!card.address_number) return 'Informe o número do endereço do titular.';
  return '';
}


function clientTermsAccepted(user){
  return Boolean(user?.client_terms_accepted) && String(user?.client_terms_version || '') === CLIENT_TERMS_VERSION;
}

function needsClientTerms(){
  return Boolean(currentUser && currentUser.role === 'client' && !clientTermsAccepted(currentUser));
}

function showClientTermsModal(){
  const modal = $('clientTermsModal');
  if(!modal) return;
  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('terms-locked');
  clientTermsReadComplete = false;
  const checkbox = $('clientTermsCheckbox');
  const btn = $('clientTermsAcceptBtn');
  const label = $('clientTermsCheckboxLabel');
  if(checkbox){ checkbox.checked = false; checkbox.disabled = true; }
  if(btn) btn.disabled = true;
  if(label) label.classList.add('disabled');
  setTimeout(updateClientTermsProgress, 80);
}

function hideClientTermsModal(){
  const modal = $('clientTermsModal');
  if(!modal) return;
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('terms-locked');
}

function updateClientTermsProgress(){
  const content = $('clientTermsContent');
  const bar = $('clientTermsProgressBar');
  const text = $('clientTermsProgressText');
  const checkbox = $('clientTermsCheckbox');
  const label = $('clientTermsCheckboxLabel');
  if(!content) return;
  const maxScroll = Math.max(content.scrollHeight - content.clientHeight, 1);
  const pct = Math.min(100, Math.round((content.scrollTop / maxScroll) * 100));
  if(bar) bar.style.width = pct + '%';
  if(text) text.textContent = pct + '%';
  if(pct >= 98 || content.scrollHeight <= content.clientHeight + 5){
    clientTermsReadComplete = true;
    if(checkbox) checkbox.disabled = false;
    if(label) label.classList.remove('disabled');
  }
  updateClientTermsAcceptButton();
}

function updateClientTermsAcceptButton(){
  const checkbox = $('clientTermsCheckbox');
  const btn = $('clientTermsAcceptBtn');
  if(btn) btn.disabled = !(clientTermsReadComplete && checkbox && checkbox.checked);
}

function bindClientTermsModal(){
  const content = $('clientTermsContent');
  if(content) content.addEventListener('scroll', updateClientTermsProgress);
  const checkbox = $('clientTermsCheckbox');
  if(checkbox) checkbox.addEventListener('change', updateClientTermsAcceptButton);
}

async function acceptClientTerms(){
  try{
    if(!currentUser || currentUser.role !== 'client') return toast('Faça login como cliente.');
    if(!clientTermsReadComplete) return toast('Leia o termo até o final para continuar.');
    const checkbox = $('clientTermsCheckbox');
    if(!checkbox || !checkbox.checked) return toast('Marque o aceite dos termos para continuar.');
    const user = await api(`/api/clients/${currentUser.id}/accept-terms`, {method:'POST'});
    currentUser = user;
    localStorage.setItem('amigopet_cliente_user', JSON.stringify(user));
    hideClientTermsModal();
    setLoggedUI();
    await refreshAll();
    showView('pet', true);
    toast('Termos aceitos com sucesso. Bem-vindo ao AmigoPet.');
  }catch(err){
    toast(err.message || 'Não foi possível registrar o aceite dos termos.');
  }
}

function enforceClientTerms(){
  if(needsClientTerms()){
    showView('home', true);
    showClientTermsModal();
    return false;
  }
  hideClientTermsModal();
  return true;
}


function clearSessions(){
  localStorage.removeItem('amigopet_user');
  localStorage.removeItem('amigopet_cliente_user');
}

function isAuthError(err){
  const message = String(err?.message || '').toLowerCase();
  return err?.status === 401
    || isCsrfError(err)
    || message.includes('csrf')
    || message.includes('autentica')
    || message.includes('sessão')
    || message.includes('sessao');
}

function resetClientDataViews(message='Faça login para carregar seus dados.'){
  if($('myPets')) setSafeHTML($('myPets'), `<div class="notice">${escapeHtml(message)}</div>`);
  if($('myWalks')) setSafeHTML($('myWalks'), `<div class="notice">${escapeHtml(message)}</div>`);
  if($('walkerCards')) setSafeHTML($('walkerCards'), `<div class="notice">${escapeHtml(message)}</div>`);
  if($('petSelect')) setSafeHTML($('petSelect'), '<option value="">Faça login para carregar seus pets</option>');
  if($('walkerSelect')) setSafeHTML($('walkerSelect'), '<option value="">Faça login para carregar passeadores</option>');
  setInviteStatus('');
}

function expireClientSession(message='Sessão expirada. Faça login novamente.'){
  currentUser = null;
  currentRequestId = null;
  selectedWalkerId = null;
  lastWalk = null;
  clearSessions();
  hideClientTermsModal();
  resetClientDataViews(message);
  setLoggedUI();
  showView('home', true);
}

function setAuthMode(mode){
  ['login','register','verify','forgotClientPassword'].forEach(name => {
    const tab = $(`${name}Tab`);
    const panel = $(`${name}Panel`);
    if(tab) tab.classList.toggle('active', name === mode);
    if(panel){
      panel.classList.toggle('active', name === mode);
      panel.classList.toggle('hidden', name !== mode);
    }
  });
}


function updateClientNotificationStatus(){
  const box = $('clientNotificationStatus');
  if(!box) return;
  const state = window.amigoPetPWA?.permissionState?.() || 'unsupported';
  const map = {
    granted: '🔔 Notificações ativas. Você será avisado sobre pagamento, mensagens e andamento do passeio.',
    denied: '🔕 Notificações bloqueadas no navegador.',
    default: '🔔 Ative as notificações para acompanhar seu passeio mesmo com o app em segundo plano.',
    unsupported: '⚠️ Este navegador não suporta notificações PWA.'
  };
  box.textContent = map[state] || map.unsupported;
}

async function enableClientNotifications(){
  const ok = await window.amigoPetPWA?.requestNotifications?.();
  updateClientNotificationStatus();
  toast(ok ? 'Notificações ativadas.' : 'Não foi possível ativar as notificações neste navegador.');
}

function clientNotificationText(type, walk){
  const pet = walk?.pet || 'seu pet';
  const messages = {
    walk_accepted: `Passeador aceitou o passeio de ${pet}.`,
    payment_confirmed: `Pagamento confirmado. O passeio de ${pet} foi liberado.`,
    walk_started: `O passeio de ${pet} foi iniciado.`,
    walk_finished: `O passeio de ${pet} foi finalizado.`,
    location_updated: `Localização do passeador atualizada.`,
    message: 'Você recebeu uma nova mensagem.'
  };
  return messages[type] || 'Atualização no seu passeio.';
}

function renderTimelineEvents(items){
  if(!items || !items.length) return '<div class="timeline-empty">Nenhum evento registrado ainda.</div>';
  return items.map(item => {
    const dt = item.created_at ? new Date(item.created_at).toLocaleString('pt-BR', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '';
    return `<div class="timeline-event">
      <div class="timeline-dot"></div>
      <div class="timeline-content">
        <strong>${escapeHtml(item.title || 'Evento')}</strong>
        <small>${escapeHtml(dt)}${item.details ? ' • ' + escapeHtml(item.details) : ''}</small>
      </div>
    </div>`;
  }).join('');
}

async function loadWalkTimeline(walkId, targetId){
  const box = $(targetId);
  if(!box || !walkId) return;
  setSafeHTML(box, '<div class="timeline-empty">Carregando timeline...</div>');
  try{
    const items = await api(`/api/walks/${walkId}/timeline`);
    setSafeHTML(box, renderTimelineEvents(items));
  }catch(err){
    setSafeHTML(box, '<div class="timeline-empty">Timeline indisponível no momento.</div>');
  }
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
    if(logged) setSafeHTML(logged, `<strong>${currentUser.full_name}</strong> conectado como <strong>Cliente</strong>`);
    if(profileName) profileName.textContent = currentUser.full_name;
    if(profilePhoto) profilePhoto.src = clientPhotoSrc(currentUser);
    if(profilePhotoLarge) profilePhotoLarge.src = clientPhotoSrc(currentUser);
    renderClientDetails();
  updateClientNotificationStatus();
    fillClientEditForm();
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
  if(!force && ['pet','walk','orders','tracking'].includes(id) && needsClientTerms()){
    id = 'home';
    setTimeout(showClientTermsModal, 50);
  }

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const view = $(id);
  if(view) view.classList.add('active');

  const btn = document.querySelector(`[data-view="${id}"]`);
  if(btn) btn.classList.add('active');

  if(currentUser && !restoringClientSession) refreshAll().catch(()=>{});
  if(id === 'tracking') setTimeout(() => { initMap(); if(lastWalk) renderMap(lastWalk); }, 250);
}

document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => showView(btn.dataset.view));
});

function getCookie(name){
  return document.cookie.split('; ').find(row => row.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';
}

async function api(path, options={}){
  return apiRequest(path, options, false);
}

async function apiRequest(path, options={}, csrfRetried=false){
  const method = String(options.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if(['POST','PUT','PATCH','DELETE'].includes(method)){
    const csrf = decodeURIComponent(getCookie('amigopet_csrf'));
    if(csrf) headers['X-CSRF-Token'] = csrf;
  }
  const res = await fetch(API + path, {
    ...options,
    headers,
    credentials: 'include',
    cache: 'no-store'
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

    const error = new Error(detail);
    error.status = res.status;
    error.path = path;
    error.data = data;
    if(options.csrfRetry && method === 'POST' && !csrfRetried && isCsrfError(error)){
      await apiRequest('/api/auth/session/current', {method:'GET'}, true);
      return apiRequest(path, options, true);
    }
    throw error;
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


let cameraStream = null;
let cameraTarget = "";

async function openCameraCapture(target){
  try{
    cameraTarget = target;
    const modal = $('cameraModal');
    const video = $('cameraVideo');
    const title = $('cameraTitle');

    if(!modal || !video) return toast('Câmera não disponível nesta tela.');

    if(title){
      const labels = {
        client: 'Tirar foto do cliente',
        editClient: 'Tirar nova foto do cliente',
        pet: 'Tirar foto do pet'
      };
      title.textContent = labels[target] || 'Tirar foto';
    }

    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: target === 'pet' ? 'environment' : 'user' },
      audio: false
    });

    video.srcObject = cameraStream;
    modal.classList.add('open');
  }catch(err){
    toast('Não foi possível abrir a câmera. Verifique a permissão do navegador.');
  }
}

function closeCameraCapture(){
  const modal = $('cameraModal');
  const video = $('cameraVideo');

  if(cameraStream){
    cameraStream.getTracks().forEach(track => track.stop());
  }

  cameraStream = null;
  cameraTarget = "";

  if(video) video.srcObject = null;
  if(modal) modal.classList.remove('open');
}

function takeCameraPhoto(){
  const video = $('cameraVideo');
  const canvas = $('cameraCanvas');

  if(!video || !canvas || !cameraTarget) return toast('Câmera não iniciada.');

  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;

  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, width, height);

  const dataUrl = canvas.toDataURL('image/jpeg', 0.82);

  if(cameraTarget === 'client'){
    clientPhotoData = dataUrl;
    const img = $('clientPhotoPreview');
    if(img){
      img.src = dataUrl;
      img.classList.remove('hidden');
    }
    safeText('clientPhotoStatus', 'Foto tirada pela câmera.');
  }

  if(cameraTarget === 'editClient'){
    editClientPhotoData = dataUrl;
    const img = $('editClientPhotoPreview');
    if(img){
      img.src = dataUrl;
      img.classList.remove('hidden');
    }
    safeText('editClientPhotoStatus', 'Nova foto tirada pela câmera.');
  }

  if(cameraTarget === 'pet'){
    petPhotoData = dataUrl;
    const img = $('petPhotoPreview');
    if(img){
      img.src = dataUrl;
      img.classList.remove('hidden');
    }
    safeText('petPhotoStatus', 'Foto do pet tirada pela câmera.');
  }

  closeCameraCapture();
  toast('Foto capturada com sucesso.');
}


function loginWithGoogle(){
  window.location.href = API + '/api/auth/google/login/client';
}

async function handleGoogleLoginCallback(){
  const params = new URLSearchParams(window.location.search);
  const googleLogin = params.get('google_login');
  const googleError = params.get('google_error');

  if(googleError){
    toast('Erro no login Google: ' + googleError);
    window.history.replaceState({}, document.title, window.location.pathname);
    return;
  }

  if(googleLogin !== 'success') return;

  try{
    const user = await api('/api/auth/session/current');
    currentUser = user;
    localStorage.setItem('amigopet_cliente_user', JSON.stringify(user));
    setLoggedUI();
    fillClientEditForm();
    await refreshAll();
    toast('Login com Google realizado.');
    window.history.replaceState({}, document.title, window.location.pathname);
    if(enforceClientTerms()) showView('pet', true);
  }catch(err){
    toast(err.message || 'Não foi possível concluir o login com Google.');
  }
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
    localStorage.setItem('amigopet_cliente_user', JSON.stringify(user));
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
  toast('A confirmação por código não é necessária nesta versão. Faça login ou crie sua conta normalmente.');
  setAuthMode('login');
}

async function resendCode(){
  toast('Reenvio de código indisponível porque a confirmação por código não é necessária nesta versão.');
  setAuthMode('login');
}


function toggleForgotPassword(){
  const email = $('loginEmail')?.value?.trim() || '';
  if($('forgotEmail')) $('forgotEmail').value = email;
  setAuthMode('forgotClientPassword');
}

async function requestPasswordReset(){
  try{
    const email = $('forgotEmail').value.trim();
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

async function confirmPasswordReset(){
  try{
    const email = $('forgotEmail').value.trim();
    const code = $('resetCode').value.trim();
    const new_password = $('resetNewPassword').value.trim();

    if(!email || !code || !new_password) return toast('Preencha e-mail, código e nova senha.');
    if(new_password.length < 6) return toast('A nova senha deve ter no mínimo 6 caracteres.');

    const result = await api('/api/auth/reset-password', {
      method:'POST',
      body: JSON.stringify({email, code, new_password})
    });

    $('loginEmail').value = email;
    $('loginPassword').value = '';
    $('resetCode').value = '';
    $('resetNewPassword').value = '';
    setAuthMode('login');

    toast(result.message || 'Senha alterada com sucesso.');
  }catch(err){
    toast(err.message || 'Não foi possível alterar a senha.');
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
    localStorage.setItem('amigopet_cliente_user', JSON.stringify(user));
    setLoggedUI();
    await refreshAll();
    toast('Login realizado.');
    showView('pet', true);
  }catch(err){
    const msg = err.message || 'Não foi possível entrar.';
    toast(msg);
  }
}

function logout(){
  api('/api/auth/logout', {method:'POST'}).catch(()=>{});
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
  setSafeHTML(box, `
    <strong>${escapeHtml(currentUser.full_name)}</strong><br>
    ${escapeHtml(currentUser.email)}<br>
    Telefone: ${escapeHtml(currentUser.phone || '-')}<br>
    Endereço: ${escapeHtml(currentUser.address || '-')}<br>
    Cidade: ${escapeHtml(currentUser.city || '-')} / ${escapeHtml(currentUser.state || '-')}<br>
    Status: <span class="badge pago">verificado</span>
  `);
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
    setSafeHTML(box, '<div class="notice">Nenhum pet cadastrado ainda.</div>');
    return;
  }
  setSafeHTML(box, pets.map(p => `
    <div class="pet-card">
      <img src="${p.photo || ''}" alt="${p.name}">
      <div>
        <strong>${p.name}</strong><br>
        <span class="muted">${p.breed || 'Raça não informada'} • ${p.size || '-'} • ${p.age || '-'}</span><br>
        <small>${p.notes || ''}</small>
      </div>
    </div>
  `).join(''));
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
  let data = null;
  try{
    if(!requireClient()) return;
    if(creatingWalk) return;
    creatingWalk = true;
    setInviteStatus('Enviando convite ao passeador...');

    const sessionUser = await api('/api/auth/session/current');
    if(!sessionUser || sessionUser.role !== 'client'){
      throw new Error('Sessão do cliente expirada. Faça login novamente.');
    }
    currentUser = sessionUser;
    localStorage.setItem('amigopet_cliente_user', JSON.stringify(sessionUser));

    const walkerId = Number($('walkerSelect')?.value || selectedWalkerId || 0);
    const petId = Number($('petSelect')?.value || 0);
    const duration = Number($('duration')?.value || 30);
    const dogsCount = Math.max(1, Number($('dogsCount')?.value || 1));
    const address = String($('address')?.value || '').trim();
    const paymentMethod = selectedPaymentMethod();

    data = {
      client_id: currentUser.id,
      walker_id: walkerId || null,
      pet_id: petId || null,
      address,
      pickup_lat: Number(currentUser.lat || -22.5884),
      pickup_lng: Number(currentUser.lng || -43.1847),
      duration_minutes: [30, 45, 60].includes(duration) ? duration : 30,
      dogs_count: dogsCount,
      notes: 'Convite criado pelo cliente.',
      payment_method: paymentMethod
    };

    if(!data.pet_id){
      setInviteStatus('Escolha um pet antes de enviar o convite.', true);
      return toast('Escolha um pet.');
    }
    if(!data.walker_id){
      setInviteStatus('Escolha um passeador antes de enviar o convite.', true);
      return toast('Escolha um passeador.');
    }
    if(!data.address){
      setInviteStatus('Informe o endereço de retirada antes de enviar o convite.', true);
      return toast('Informe o endereço.');
    }
    if(paymentMethod === 'CREDIT_CARD'){
      const card = collectCreditCardData();
      const cardError = validateCreditCardData(card);
      if(cardError){
        setInviteStatus(cardError, true);
        return toast(cardError);
      }
      data.credit_card = card;
    }

    console.info('[AmigoPet] Enviando convite /api/walks', {...data, credit_card: data.credit_card ? '[dados protegidos]' : undefined});

    const walk = await api('/api/walks', {
      method:'POST',
      csrfRetry: true,
      body: JSON.stringify(data)
    });

    currentRequestId = walk.id;
    lastWalk = walk;
    renderCurrentWalk(walk);
    renderMap(walk);
    await refreshAll();
    toast(`Convite #${walk.id} enviado. R$ ${Number(walk.estimated_price).toFixed(2)}`);
    setInviteStatus(`Convite #${walk.id} enviado ao passeador.`);
    showView('tracking', true);
  }catch(err){
    const message = friendlyWalkSubmitError(err);
    console.error('[AmigoPet] Falha ao enviar convite /api/walks', {
      message,
      detail: err.message || '',
      status: err.status || null,
      payload: data ? {...data, credit_card: data.credit_card ? '[dados protegidos]' : undefined} : null,
      csrfPresente: Boolean(getCookie('amigopet_csrf')),
      clienteLogado: Boolean(currentUser && currentUser.role === 'client')
    });
    setInviteStatus(message, true);
    toast(message);
  }finally{
    creatingWalk = false;
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
    toast(walk.payment_status === 'pago' ? 'Pagamento confirmado automaticamente.' : 'Pagamento ainda aguardando confirmação do Asaas.');
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
    setSafeHTML(mapEl, '<div class="map-fallback">Mapa indisponível. Verifique a conexão com a internet.</div>');
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
    setSafeHTML(box, `<strong>#${w.id} • ${w.pet || 'Pet'}</strong><br>
    Cliente: ${w.client}<br>
    Passeador: ${w.walker}<br>
    Status: <span class="badge ${w.status}">${w.status}</span> <span class="badge aceito">${activeLabel}</span><br>
    Pagamento: <span class="badge ${w.payment_status}">${w.payment_status}</span><br>
    Distância do pedido: ${w.distance_km} km • ${w.duration_minutes} min • R$ ${Number(w.estimated_price).toFixed(2)}<br>
    Distância ao cliente: <strong>${kmLive.toFixed(2)} km</strong><br>
    Previsão de chegada: <strong>${eta} min</strong><br>
    Localização passeador: ${Number(w.walker_lat || -22.5900).toFixed(5)}, ${Number(w.walker_lng || -43.1810).toFixed(5)}
    ${clientRatingBox(w)}
    <div class="walk-timeline"><h3>📋 Timeline do passeio</h3><div id="walkTimelineBox"></div></div>`);
    loadWalkTimeline(w.id, 'walkTimelineBox').catch(()=>{});
  }

  const pixBox = $('pixBox');
  if(pixBox){
    const isCard = String(w.payment_method || '').toUpperCase() === 'CREDIT_CARD';
    const pixData = w.pixQrCode || w.pix_qr_code || w.asaas_pix || {};
    const copy = isCard ? '' : (w.pix_code || w.mp_qr_code || w.qr_code || w.qrCode || pixData.payload || pixData.copyPaste || pixData.encodedPayload || '');
    const base64 = isCard ? '' : (w.mp_qr_code_base64 || w.qr_code_base64 || w.qrCodeBase64 || pixData.encodedImage || '');
    const ticketUrl = w.mp_ticket_url || w.invoiceUrl || w.invoice_url || w.payment_url || w.bankSlipUrl || '';
    const errorText = w.mp_status_detail && String(w.mp_status_detail).toLowerCase() !== 'pix' ? `<div class="notice" style="margin-top:10px;color:#92400e;">Retorno do pagamento: ${escapeHtml(w.mp_status_detail)}</div>` : '';
    let qrImg = '';
    if(base64){
      const src = String(base64).startsWith('data:image') ? base64 : `data:image/png;base64,${base64}`;
      qrImg = `<img alt="QR Code PIX Asaas" src="${src}" style="max-width:240px;width:100%;display:block;margin:10px auto;border-radius:16px;border:1px solid #e2e8f0;">`;
    }else if(copy && !String(copy).includes('PIX-SIMULADO')){
      qrImg = `<img alt="QR Code PIX" src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(copy)}" style="max-width:240px;width:100%;display:block;margin:10px auto;border-radius:16px;border:1px solid #e2e8f0;">`;
    }
    const ticket = ticketUrl ? `<br><a href="${escapeHtml(ticketUrl)}" target="_blank" rel="noopener">Abrir pagamento Asaas</a>` : '';
    const copyText = isCard ? 'Pagamento por cartão enviado ao Asaas. Aguarde a confirmação.' : (copy || 'Aguardando geração do PIX Asaas. Clique em Verificar/Gerar PIX.');
    const safeCopy = String(copy).replace(/`/g, '').replace(/\\/g, '\\\\');
    const copyButton = copy ? `<button type="button" class="ghost" style="margin-top:10px" onclick="navigator.clipboard.writeText(\`${safeCopy}\`); toast('Código PIX copiado')">Copiar código PIX</button>` : '';
    const payButtonLabel = isCard ? 'Verificar cartão' : 'Verificar/Gerar PIX';
    const payButton = w.id && w.payment_status !== 'pago' ? `<button type="button" class="warn" style="margin-top:10px;margin-left:8px" onclick="payWalk(${w.id})">${payButtonLabel}</button>` : '';
    setSafeHTML(pixBox, `${qrImg}<div style="word-break:break-all;white-space:pre-wrap;background:#0f172a;color:#d1fae5;border-radius:16px;padding:12px;font-size:12px;line-height:1.35;">${escapeHtml(copyText)}</div>${copyButton}${payButton}${ticket}${errorText}`);
  }
  renderMap(w);
}

function ratingStarsSelect(idPrefix){
  return `<select id="${idPrefix}Rating" aria-label="Nota da avaliação">
    <option value="5">⭐⭐⭐⭐⭐ Excelente</option>
    <option value="4">⭐⭐⭐⭐ Muito bom</option>
    <option value="3">⭐⭐⭐ Regular</option>
    <option value="2">⭐⭐ Ruim</option>
    <option value="1">⭐ Muito ruim</option>
  </select>`;
}

function clientRatingBox(w){
  if(!w || w.status !== 'finalizado' || !w.walker_id || !currentUser) return '';
  return `<div class="rating-box">
    <h3>⭐ Avaliar passeador</h3>
    <p class="muted">Como foi o passeio com ${escapeHtml(w.walker || 'o passeador')}?</p>
    ${ratingStarsSelect('clientWalk')}
    <textarea id="clientWalkRatingComment" placeholder="Comentário opcional sobre o passeio"></textarea>
    <button class="full ok" type="button" onclick="sendClientRating(${w.id}, ${w.walker_id})">Enviar avaliação</button>
  </div>`;
}

async function sendClientRating(walkId, targetId){
  try{
    if(!requireClient()) return;
    const rating = Number($('clientWalkRatingRating')?.value || 5);
    const comment = $('clientWalkRatingComment')?.value?.trim() || '';
    await api(`/api/walks/${walkId}/ratings`, {
      method:'POST',
      body: JSON.stringify({rater_id: currentUser.id, target_id: targetId, rating, comment})
    });
    toast('Avaliação enviada com sucesso. Obrigado!');
    await refreshAll();
  }catch(err){
    toast(err.message || 'Não foi possível enviar a avaliação.');
  }
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
  const previousWalkerId = String($('walkerSelect')?.value || selectedWalkerId || '');
  const previousPetId = String($('petSelect')?.value || '');

  const loadPart = async (label, path) => {
    try{
      const data = await api(path);
      return Array.isArray(data) ? data : [];
    }catch(e){
      e.listLabel = label;
      throw e;
    }
  };

  const results = await Promise.allSettled([
    loadPart('passeadores', '/api/users?role=walker'),
    loadPart('pedidos', '/api/walks'),
    loadPart('pets', `/api/pets?owner_id=${currentUser.id}`)
  ]);

  const authFailure = results.find(result => result.status === 'rejected' && isAuthError(result.reason));
  if(authFailure){
    const e = authFailure.reason;
    console.error('[AmigoPet] Falha ao carregar dados do cliente', {
      status: e.status,
      path: e.path,
      message: e.message
    });
    expireClientSession('Sessão expirada. Faça login novamente para carregar pets, passeadores e pedidos.');
    return;
  }

  const failedParts = results
    .map((result, index) => ({result, label: ['passeadores', 'pedidos', 'pets'][index]}))
    .filter(item => item.result.status === 'rejected');

  if(failedParts.length){
    console.error('[AmigoPet] Falha parcial ao carregar dados do cliente', failedParts.map(item => ({
      label: item.label,
      status: item.result.reason?.status,
      path: item.result.reason?.path,
      message: item.result.reason?.message
    })));
  }

  walkers = results[0].status === 'fulfilled' ? results[0].value : [];
  walks = results[1].status === 'fulfilled' ? results[1].value : [];
  pets = results[2].status === 'fulfilled' ? results[2].value : [];

  const availableWalkerList = walkers.filter(w => w.available !== false);

  renderClientDetails();
  renderPets(pets);

  if($('walkerSelect')){
    if(results[0].status === 'rejected'){
      setSafeHTML($('walkerSelect'), '<option value="">Não foi possível carregar passeadores</option>');
    }else{
      setSafeHTML($('walkerSelect'), `<option value="">Escolha um passeador</option>` + availableWalkerList.map(w =>
        `<option value="${w.id}">${w.full_name} • ⭐ ${w.rating} • ${w.neighborhood || '-'}</option>`
      ).join(''));
    }
    if(previousWalkerId && availableWalkerList.some(w => String(w.id) === previousWalkerId)){
      $('walkerSelect').value = previousWalkerId;
      selectedWalkerId = Number(previousWalkerId);
    }
  }

  if($('walkerCards')){
    if(results[0].status === 'rejected'){
      setSafeHTML($('walkerCards'), '<div class="notice">Não foi possível carregar passeadores agora. Tente novamente em instantes.</div>');
    }else{
      const visibleWalkers = availableWalkerList.slice(0, 6);
      setSafeHTML($('walkerCards'), `
      <div class="notice walker-premium-notice">
        <strong>${availableWalkerList.length}</strong> passeador(es) disponíveis perto de você.
      </div>
      <div class="walker-premium-grid">
        ${visibleWalkers.map(w => {
          const km = kmBetween(
            Number(currentUser?.lat || -22.5884),
            Number(currentUser?.lng || -43.1847),
            Number(w.lat || -22.5900),
            Number(w.lng || -43.1810)
          );
          const eta = etaMinutesFromKm(km);
          const name = escapeHtml(w.full_name || 'Passeador');
          const city = escapeHtml(w.city || '-');
          const neighborhood = escapeHtml(w.neighborhood || '-');
          const bio = escapeHtml(w.bio || 'Passeador disponível para cuidar do seu pet.');
          const rating = Number(w.rating || 5).toFixed(1);
          const photo = photoOrAvatar(w, '🚶').replace('width:44px;height:44px;border-radius:14px;', 'width:92px;height:92px;border-radius:26px;');
          return `<div class="walker-card walker-premium-card" data-walker-card="${w.id}">
            <div class="walker-premium-photo-wrap">
              ${photo}
              <span class="walker-premium-badge">✓ Verificado</span>
            </div>
            <div class="walker-premium-body">
              <div class="walker-premium-title-row">
                <div>
                  <strong class="walker-premium-name">${name}</strong>
                  <small class="walker-premium-area">${neighborhood} • ${city}</small>
                </div>
                <span class="walker-premium-rating">⭐ ${rating}</span>
              </div>
              <p class="walker-premium-bio">${bio}</p>
              <div class="walker-premium-stats">
                <span>📍 ${km.toFixed(1)} km</span>
                <span>🕒 ${eta} min</span>
                <span>🐾 Disponível</span>
              </div>
              <button type="button" class="walker-premium-select" onclick="selectWalker(${w.id})">Escolher passeador</button>
            </div>
          </div>`;
        }).join('')}
      </div>`);
    }
  }

  if($('petSelect')){
    if(results[2].status === 'rejected'){
      setSafeHTML($('petSelect'), '<option value="">Não foi possível carregar pets</option>');
    }else{
      setSafeHTML($('petSelect'), `<option value="">Escolha o pet</option>` + pets.map(p =>
        `<option value="${p.id}">${p.name} • ${p.size}</option>`
      ).join(''));
    }
    if(previousPetId && pets.some(p => String(p.id) === previousPetId)){
      $('petSelect').value = previousPetId;
    }
  }

  const myWalks = walks.filter(w => w.client_id === currentUser.id);

  if($('myWalks')){
    if(results[1].status === 'rejected'){
      setSafeHTML($('myWalks'), '<div class="notice">Não foi possível carregar pedidos agora. Tente novamente em instantes.</div>');
    }else{
      setSafeHTML($('myWalks'), myWalks.length ? myWalks.map(walkItem).join('') : '<div class="notice">Nenhum pedido criado ainda.</div>');
    }
  }

  if(!lastWalk && myWalks[0]){
    lastWalk = myWalks[0];
    currentRequestId = myWalks[0].id;
    renderCurrentWalk(myWalks[0]);
    renderMap(myWalks[0]);
  }
}

function canUseChat(walk){
  return walk && ['aceito','em_andamento','finalizado'].includes(String(walk.status || ''));
}

function chatStatusText(walk){
  if(!walk) return 'Selecione um pedido para conversar.';
  if(!canUseChat(walk)) return '🔒 Chat liberado após o aceite do passeio.';
  return `Chat com ${escapeHtml(walk.walker || 'passeador')} • ${escapeHtml(walk.pet || 'pet')}`;
}

function updateChatHeader(walk){
  const title = $('chatTitle');
  const sub = $('chatSubtitle');
  if(title) title.textContent = walk ? `Passeio #${walk.id}` : 'Chat interno';
  if(sub) sub.textContent = walk ? chatStatusText(walk).replace(/<[^>]*>/g, '') : 'Selecione um pedido';
}

function renderChatMessage(m){
  const mine = currentUser && Number(m.sender_id) === Number(currentUser.id);
  const time = m.created_at ? new Date(m.created_at).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) : '';
  const read = m.read_at ? '✓✓' : '✓';
  const readClass = m.read_at ? 'read' : '';
  const avatarSeed = encodeURIComponent(m.sender_name || (mine ? currentUser.full_name : 'Passeador'));
  const avatar = m.sender_photo || `https://api.dicebear.com/8.x/initials/svg?seed=${avatarSeed}&backgroundColor=ccfbf1,dbeafe,fef3c7`;
  return `<div class="chat-row ${mine ? 'mine' : 'theirs'}">
    ${mine ? '' : `<img class="chat-avatar" src="${escapeHtml(avatar)}" alt="${escapeHtml(m.sender_name || 'Usuário')}">`}
    <div class="chat-bubble-pro">
      <div class="chat-sender">${mine ? 'Você' : escapeHtml(m.sender_name || 'Passeador')}</div>
      <div class="chat-text">${escapeHtml(m.text)}</div>
      <div class="chat-meta"><span>${time}</span>${mine ? `<span class="ticks ${readClass}">${read}</span>` : ''}</div>
    </div>
  </div>`;
}

function scrollChatToBottom(){
  const box = $('chatMessages');
  if(box) setTimeout(() => { box.scrollTop = box.scrollHeight; }, 30);
}

function toggleChat(){
  const box = $('chatBox');
  if(!box) return;
  box.classList.toggle('open');
  if(box.classList.contains('open')) loadMessages();
}

async function openChat(requestId){
  currentRequestId = requestId;
  await loadWalk(requestId).catch(()=>{});
  const box = $('chatBox');
  if(box) box.classList.add('open');
  await loadMessages();
}

async function loadMessages(){
  const chatBody = $('chatMessages');
  if(!chatBody) return;
  if(!currentRequestId){
    updateChatHeader(null);
    setSafeHTML(chatBody, '<div class="chat-locked">Abra uma solicitação primeiro.</div>');
    return;
  }

  const walk = lastWalk && Number(lastWalk.id) === Number(currentRequestId) ? lastWalk : await api(`/api/walks/${currentRequestId}`);
  lastWalk = walk;
  updateChatHeader(walk);

  if(!canUseChat(walk)){
    setSafeHTML(chatBody, `<div class="chat-locked">🔒 Chat será liberado após o pagamento confirmado e aceite do passeador.<br><small>Status atual: ${escapeHtml(walk.status || '-')}</small></div>`);
    return;
  }

  const msgs = await api(`/api/messages/${currentRequestId}`);
  setSafeHTML(chatBody, msgs.length ? msgs.map(renderChatMessage).join('') : '<div class="chat-locked">Nenhuma mensagem ainda. Envie a primeira mensagem.</div>');
  await api(`/api/messages/${currentRequestId}/read/${currentUser.id}`, {method:'POST'}).catch(()=>{});
  scrollChatToBottom();
}

function sendTypingSignal(isTyping=true){
  try{
    if(!chatSocket || chatSocket.readyState !== WebSocket.OPEN || !currentRequestId || !currentUser) return;
    chatSocket.send(JSON.stringify({type:'typing', request_id: currentRequestId, sender_id: currentUser.id, sender_role: currentUser.role, is_typing: Boolean(isTyping)}));
  }catch(e){}
}

function handleChatTyping(){
  clearTimeout(chatTypingTimer);
  sendTypingSignal(true);
  chatTypingTimer = setTimeout(() => sendTypingSignal(false), 1200);
}

async function sendMessage(){
  try{
    if(!requireClient()) return;
    if(!currentRequestId) return toast('Abra uma solicitação primeiro.');

    const text = $('chatText').value.trim();
    if(!text) return;

    await api('/api/messages', {
      method:'POST',
      body: JSON.stringify({request_id: currentRequestId, sender_id: currentUser.id, text, message_type:'text'})
    });

    $('chatText').value = '';
    sendTypingSignal(false);
    await loadMessages();
  }catch(err){
    toast(err.message);
  }
}

function connectWS(){
  try{
    const ws = new WebSocket(WS_URL);
    chatSocket = ws;
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
        message:'Nova mensagem',
        rating_created:'Avaliação recebida'
      };

      if(data.type === 'typing' && Number(data.request_id) === Number(currentRequestId) && currentUser && Number(data.sender_id) !== Number(currentUser.id)){
        const t = $('chatTyping');
        if(t){
          t.textContent = data.is_typing ? 'Digitando...' : '';
          clearTimeout(chatTypingClearTimer);
          if(data.is_typing) chatTypingClearTimer = setTimeout(() => t.textContent = '', 1800);
        }
        return;
      }
      if(data.type === 'messages_read' && Number(data.request_id) === Number(currentRequestId)){
        loadMessages().catch(()=>{});
        return;
      }
      if(data.type === 'walker_availability_changed'){
        const status = data.walker?.available === false ? 'ficou offline' : 'está online';
        toast(`Passeador ${status}.`);
      }else if(data.type) toast(labels[data.type] || 'Atualização recebida');

      if(data.type && data.walk && currentUser && data.walk.client_id === currentUser.id){
        const shouldNotify = window.amigoPetPWA?.shouldNotifyInBackground?.() || document.hidden;
        if(shouldNotify){
          window.amigoPetPWA?.notify('🐾 AmigoPet Cliente', clientNotificationText(data.type, data.walk), '/', {tag:`client-walk-${data.walk.id}-${data.type}`});
        }
      }

      if(data.walk && currentUser && data.walk.client_id === currentUser.id){
        lastWalk = data.walk;
        currentRequestId = data.walk.id;
        renderCurrentWalk(data.walk);
        renderMap(data.walk);
      }

      if(currentUser) await refreshAll();
      if(data.type === 'message' && Number(data.request_id || data.message?.request_id) === Number(currentRequestId)) loadMessages();
    };
    ws.onclose = () => setTimeout(connectWS, 2500);
  }catch(e){}
}


async function restoreClientSession(){
  restoringClientSession = true;
  try{
    const freshUser = await api('/api/auth/session/current');

    if(freshUser && freshUser.role === 'client'){
      currentUser = freshUser;
      localStorage.setItem('amigopet_cliente_user', JSON.stringify(freshUser));
      localStorage.removeItem('amigopet_user');
      setLoggedUI();
      fillClientEditForm();
      await refreshAll().catch(()=>{});
      if(enforceClientTerms()) showView('pet', true);
      return true;
    }
  }catch(e){
    console.info('[AmigoPet] Sessão do cliente não restaurada pelo servidor', {
      status: e.status,
      message: e.message
    });
  }finally{
    restoringClientSession = false;
  }

  expireClientSession('Faça login para acessar seus pets, passeadores e pedidos.');
  return false;
}

async function bootstrapClientApp(){
  bindClientTermsModal();
  await handleGoogleLoginCallback().catch(()=>{});
  await restoreClientSession().catch(()=>{});
  loadPricing().catch(()=>{});
  connectWS();
  updateClientNotificationStatus();
  document.addEventListener('visibilitychange', updateClientNotificationStatus);
  const chatInput = $('chatText');
  if(chatInput) chatInput.addEventListener('input', handleChatTyping);
}

bootstrapClientApp();

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

    setSafeHTML(box, `
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
    `);
  }catch(e){
    console.error('Erro ao carregar preços:', e);

    setSafeHTML(box, `
      <div class="notice">
        Não foi possível carregar os valores agora.
        <br><br>
        Tente atualizar a página em alguns segundos.
      </div>
    `);
  }
}


// ===== AmigoPet: bindings seguros para botões sem onclick =====
// Este bloco evita que botões fiquem sem ação quando o HTML não tem onclick
// ou quando o navegador/PWA carrega uma versão com handlers removidos.
(function bindAmigoPetClientActions(){
  function bindById(id, handler){
    const el = document.getElementById(id);
    if(el && !el.dataset.boundAmigopet){
      el.dataset.boundAmigopet = '1';
      el.addEventListener('click', function(ev){
        ev.preventDefault();
        handler();
      });
    }
  }

  function bindByText(textPart, handler){
    const needle = String(textPart || '').toLowerCase();
    document.querySelectorAll('button, a, [role="button"]').forEach(function(el){
      const label = String(el.textContent || el.value || '').trim().toLowerCase();
      if(label.includes(needle) && !el.dataset.boundAmigopet){
        el.dataset.boundAmigopet = '1';
        el.addEventListener('click', function(ev){
          ev.preventDefault();
          handler();
        });
      }
    });
  }

  function bindAll(){
    // Expõe funções para onclick antigo do HTML.
    window.login = login;
    window.loginWithGoogle = loginWithGoogle;
    window.logout = logout;
    window.registerClient = registerClient;
    window.verifyCode = verifyCode;
    window.resendCode = resendCode;
    window.toggleForgotPassword = toggleForgotPassword;
    window.requestPasswordReset = requestPasswordReset;
    window.confirmPasswordReset = confirmPasswordReset;
    window.fillClientDemo = fillClientDemo;
    window.createPet = createPet;
    window.createWalk = createWalk;
    window.payWalk = payWalk;
    window.simulateMove = simulateMove;
    window.toggleClientEdit = toggleClientEdit;
    window.updateClientProfile = updateClientProfile;
    window.openCameraCapture = openCameraCapture;
    window.closeCameraCapture = closeCameraCapture;
    window.takeCameraPhoto = takeCameraPhoto;
    window.showView = showView;

    bindById('loginBtn', login);
    bindById('btnLogin', login);
    bindById('logoutBtn', logout);
    bindById('registerBtn', registerClient);
    bindById('btnRegister', registerClient);
    bindById('verifyBtn', verifyCode);
    bindById('resendCodeBtn', resendCode);
    bindById('forgotPasswordBtn', toggleForgotPassword);
    bindById('btnForgotPassword', toggleForgotPassword);
    bindById('requestPasswordResetBtn', requestPasswordReset);
    bindById('btnRequestPasswordReset', requestPasswordReset);
    bindById('generateResetCodeBtn', requestPasswordReset);
    bindById('confirmPasswordResetBtn', confirmPasswordReset);
    bindById('btnConfirmPasswordReset', confirmPasswordReset);
    bindById('createPetBtn', createPet);
    bindById('btnCreatePet', createPet);
    bindById('createWalkBtn', createWalk);
    bindById('btnCreateWalk', createWalk);
    bindById('updateClientBtn', updateClientProfile);
    bindById('btnUpdateClient', updateClientProfile);
    const paymentMethod = $('paymentMethod');
    if(paymentMethod && !paymentMethod.dataset.boundAmigopetPayment){
      paymentMethod.dataset.boundAmigopetPayment = '1';
      paymentMethod.addEventListener('change', toggleCreditCardFields);
      toggleCreditCardFields();
    }

    bindByText('entrar com google', loginWithGoogle);
    bindByText('gerar código de recuperação', requestPasswordReset);
    bindByText('recuperar senha', toggleForgotPassword);
    bindByText('alterar senha', confirmPasswordReset);
    bindByText('cadastrar pet', createPet);
    bindByText('solicitar passeio', createWalk);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', bindAll);
  }else{
    bindAll();
  }

  // Se o PWA ou troca de abas recriar partes da tela, rebinda sem duplicar.
  setTimeout(bindAll, 600);
  setTimeout(bindAll, 1800);
})();


window.acceptClientTerms = acceptClientTerms;
