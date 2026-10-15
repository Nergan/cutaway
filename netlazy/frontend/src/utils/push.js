import api from './api.js';
import { Capacitor } from '@capacitor/core';
import { useStore } from '../store/state.js';

let nativeListeners = false;
let nativeMarker = '';
let nativeToken = '';
let webMarker = '';

function hubOrigin() {
  if (Capacitor.isNativePlatform()) {
    const apiRoot = String(import.meta.env.VITE_API_URL || 'https://nargan-projects.hf.space/netlazy/api');
    return new URL(apiRoot).origin;
  }
  return window.location.origin;
}

function inboxOpenPath() {
  if (Capacitor.isNativePlatform()) return '/netlazy/inbox';
  const segments = window.location.pathname.split('/');
  if (segments[segments.length - 1] === '') segments.pop();
  while (segments.length && ['feed', 'profile', 'inbox', 'privacy', 'config', 'welcome'].includes(segments[segments.length - 1])) {
    segments.pop();
  }
  return `${segments.join('/')}/inbox`;
}

export function pushPlatform() {
  if (Capacitor.getPlatform() === 'android' || /Android/i.test(navigator.userAgent || '')) return 'android';
  if (/Windows/i.test(navigator.userAgent || '')) return 'windows';
  return 'web';
}

function sameApplicationKey(subscription, keyBytes) {
  const current = subscription.options && subscription.options.applicationServerKey;
  if (!current) return false;
  const bytes = new Uint8Array(current);
  if (bytes.length !== keyBytes.length) return false;
  for (let i = 0; i < bytes.length; i += 1) {
    if (bytes[i] !== keyBytes[i]) return false;
  }
  return true;
}

function serviceWorkerTarget() {
  const path = window.location.pathname || '/';
  if (path.includes('/static/')) {
    const base = import.meta.env.BASE_URL || '/';
    const scope = base.endsWith('/') ? base : `${base}/`;
    return { script: `${scope}sw.js`, scope };
  }
  const segments = path.split('/');
  if (segments[segments.length - 1] === '') segments.pop();
  while (segments.length && ['feed', 'profile', 'inbox', 'privacy', 'config', 'welcome'].includes(segments[segments.length - 1])) {
    segments.pop();
  }
  const root = segments.join('/') || '';
  return { script: `${root}/sw.js`, scope: `${root}/` };
}

function waitUntilActive(registration) {
  if (registration.active) return Promise.resolve();
  const worker = registration.installing || registration.waiting;
  if (!worker || worker.state === 'activated') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('push worker timeout')), 8000);
    worker.addEventListener('statechange', () => {
      if (worker.state === 'activated') {
        clearTimeout(timer);
        resolve();
      } else if (worker.state === 'redundant') {
        clearTimeout(timer);
        reject(new Error('push worker stopped'));
      }
    });
  });
}

function decodeKey(value) {
  const pad = '='.repeat((4 - (value.length % 4)) % 4);
  const b64 = value.replace(/-/g, '+').replace(/_/g, '/') + pad;
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

async function postSubscription(body) {
  await api.post('/push/subscriptions', body);
}

export async function syncDevicePush() {
  const store = useStore();
  if (!store.state.pushEnabled || !store.state.isRegistered) return;
  if (Capacitor.getPlatform() === 'android') {
    if (import.meta.env.VITE_FCM_ENABLED === 'true') await syncAndroidPush(store);
    return;
  }
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    store.addToast(store.t('push_unavailable'), 'bi-bell-slash');
    return;
  }
  const permission = Notification.permission === 'granted'
    ? 'granted'
    : await Notification.requestPermission();
  if (permission !== 'granted') {
    store.addToast(store.t('push_permission_denied'), 'bi-bell-slash');
    return;
  }
  const target = serviceWorkerTarget();
  const registration = await navigator.serviceWorker.register(target.script, { scope: target.scope });
  await waitUntilActive(registration);
  const active = registration;
  const keyRes = await api.get('/push/key');
  const applicationServerKey = decodeKey(keyRes.data.public_key);
  let existing = await active.pushManager.getSubscription();
  if (existing && !sameApplicationKey(existing, applicationServerKey)) {
    await existing.unsubscribe();
    existing = null;
  }
  const subscription = existing || await active.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey,
  });
  const json = subscription.toJSON();
  const marker = `${json.endpoint}|${store.state.lang}|${inboxOpenPath()}`;
  if (marker === webMarker) return;
  await postSubscription({
    platform: pushPlatform(),
    transport: 'webpush',
    endpoint: json.endpoint,
    p256dh: json.keys && json.keys.p256dh,
    auth: json.keys && json.keys.auth,
    open_path: inboxOpenPath(),
    origin: hubOrigin(),
    lang: store.state.lang,
  });
  webMarker = marker;
}

async function syncAndroidPush(store) {
  const { PushNotifications } = await import('@capacitor/push-notifications');
  if (!nativeListeners) {
    await PushNotifications.addListener('registration', (token) => {
      const current = useStore();
      if (!current.state.pushEnabled || !current.state.isRegistered || !token?.value) return;
      const marker = `${token.value}|${current.state.lang}|${inboxOpenPath()}`;
      if (marker === nativeMarker) return;
      nativeMarker = marker;
      nativeToken = token.value;
      postSubscription({
        platform: 'android',
        transport: 'fcm',
        token: token.value,
        open_path: inboxOpenPath(),
        origin: hubOrigin(),
        lang: current.state.lang,
      }).catch(() => {
        nativeMarker = '';
      });
    });
    await PushNotifications.addListener('registrationError', () => {
      useStore().addToast(useStore().t('push_unavailable'), 'bi-bell-slash');
    });
    await PushNotifications.addListener('pushNotificationActionPerformed', () => {
      useStore().state.currentView = 'inbox';
    });
    await PushNotifications.addListener('pushNotificationReceived', (notification) => {
      const title = notification?.title || notification?.data?.title;
      if (title) useStore().addToast(title, 'bi-bell');
    });
    nativeListeners = true;
  }
  try {
    await PushNotifications.createChannel({
      id: 'handshakes',
      name: store.t('push_notifications'),
      description: store.t('push_notifications'),
      importance: 4,
      visibility: 1,
      vibration: true,
    });
  } catch (e) {}
  let perm = await PushNotifications.checkPermissions();
  if (perm.receive !== 'granted') perm = await PushNotifications.requestPermissions();
  if (perm.receive !== 'granted') {
    store.addToast(store.t('push_permission_denied'), 'bi-bell-slash');
    return;
  }
  nativeMarker = '';
  await PushNotifications.register();
}

export async function removeDevicePush() {
  const store = useStore();
  webMarker = '';
  nativeMarker = '';
  const token = nativeToken;
  nativeToken = '';
  try {
    if (token && store.state.userId) {
      await api.delete('/push/subscriptions', { data: { token } });
    }
  } catch (e) {}
  try {
    if (store.state.userId && 'serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.getRegistration();
      const subscription = await registration?.pushManager?.getSubscription();
      if (subscription) {
        await api.delete('/push/subscriptions', { data: { endpoint: subscription.endpoint } });
        await subscription.unsubscribe();
      }
    }
  } catch (e) {}
  if (Capacitor.getPlatform() !== 'android' || import.meta.env.VITE_FCM_ENABLED !== 'true') return;
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications');
    await PushNotifications.unregister();
    await PushNotifications.removeAllListeners();
    nativeListeners = false;
  } catch (e) {}
}
