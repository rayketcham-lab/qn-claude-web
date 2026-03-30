/* QN Code Assistant - Service Worker Registration */

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(registrations => {
        registrations.forEach(r => r.unregister());
    }).then(() => {
        navigator.serviceWorker.register('/static/sw.js?v=1.5.1').catch(() => {});
    });
}
