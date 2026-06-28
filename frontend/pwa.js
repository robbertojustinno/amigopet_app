(function(){
  const APP_NAME = 'AmigoPet';
  const SW_VERSION = 'patch-006-avaliacoes';

  async function registerServiceWorker(){
    if (!('serviceWorker' in navigator)) return null;
    try{
      const registration = await navigator.serviceWorker.register('/sw.js?v=' + SW_VERSION, { scope: '/' });
      try { await registration.update(); } catch(e) {}
      return registration;
    }catch(err){
      console.warn('PWA: falha ao registrar service worker', err);
      return null;
    }
  }

  function notificationSupported(){
    return 'Notification' in window && 'serviceWorker' in navigator;
  }

  function permissionState(){
    if (!('Notification' in window)) return 'unsupported';
    return Notification.permission;
  }

  async function requestNotifications(){
    if (!notificationSupported()) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;
    try{
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }catch(err){
      console.warn('PWA: permissão de notificação negada/indisponível', err);
      return false;
    }
  }

  async function notify(title, body, url, options={}){
    if (!notificationSupported()) return false;
    if (Notification.permission !== 'granted') return false;

    const payload = {
      type: 'SHOW_NOTIFICATION',
      title: title || APP_NAME,
      body: body || 'Nova atualização no AmigoPet.',
      url: url || location.pathname || '/',
      tag: options.tag || 'amigopet-update',
      requireInteraction: Boolean(options.requireInteraction),
      silent: Boolean(options.silent)
    };

    try{
      const registration = await navigator.serviceWorker.ready;
      if (registration?.showNotification) {
        await registration.showNotification(payload.title, {
          body: payload.body,
          icon: '/static/assets/amigopet-icon.svg',
          badge: '/static/assets/amigopet-icon.svg',
          tag: payload.tag,
          renotify: true,
          requireInteraction: payload.requireInteraction,
          silent: payload.silent,
          data: { url: payload.url }
        });
        return true;
      }
    }catch(err){
      console.warn('PWA: falha ao exibir notificação via service worker', err);
    }

    try{
      new Notification(payload.title, {
        body: payload.body,
        icon: '/static/assets/amigopet-icon.svg',
        tag: payload.tag,
        data: { url: payload.url }
      });
      return true;
    }catch(err){
      console.warn('PWA: falha ao exibir notificação local', err);
      return false;
    }
  }

  function shouldNotifyInBackground(){
    return document.hidden || !document.hasFocus();
  }

  window.amigoPetPWA = {
    register: registerServiceWorker,
    requestNotifications,
    notificationSupported,
    permissionState,
    notify,
    shouldNotifyInBackground
  };

  window.addEventListener('load', () => {
    registerServiceWorker();
  });
})();
