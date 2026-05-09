(function(){
  const APP_NAME = 'AmigoPet';

  async function registerServiceWorker(){
    if (!('serviceWorker' in navigator)) return null;
    try{
      const registration = await navigator.serviceWorker.register('/sw.js?v=final-pagamento-fotos', { scope: '/' });
      try { await registration.update(); } catch(e) {}
      return registration;
    }catch(err){
      console.warn('PWA: falha ao registrar service worker', err);
      return null;
    }
  }

  async function ensureNotificationPermission(){
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;
    try{
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }catch(err){
      return false;
    }
  }

  async function notify(title, body, url){
    const granted = await ensureNotificationPermission();
    if (!granted) return;

    const payload = {
      type: 'SHOW_NOTIFICATION',
      title: title || APP_NAME,
      body: body || 'Nova atualização no AmigoPet.',
      url: url || location.pathname || '/'
    };

    if (navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage(payload);
      return;
    }

    try{
      const registration = await navigator.serviceWorker?.ready;
      if (registration?.showNotification) {
        await registration.showNotification(payload.title, {
          body: payload.body,
          icon: '/static/assets/amigopet-icon.svg',
          badge: '/static/assets/amigopet-icon.svg',
          data: { url: payload.url }
        });
      }
    }catch(err){
      console.warn('PWA: falha ao exibir notificação', err);
    }
  }

  window.amigoPetPWA = {
    register: registerServiceWorker,
    requestNotifications: ensureNotificationPermission,
    notify
  };

  window.addEventListener('load', () => {
    registerServiceWorker();
  });
})();
