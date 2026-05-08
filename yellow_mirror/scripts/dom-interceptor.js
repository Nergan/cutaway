// yellow_mirror/scripts/dom-interceptor.js
(function() {
  'use strict';

  // Prevent the target page from accessing window.top or parent
  Object.defineProperty(window, 'top', { get: () => window });
  Object.defineProperty(window, 'parent', { get: () => window });

  // Override location to capture redirects and SPA navigation
  const originalLocation = window.location;
  const proxyBase = '/yellow-mirror/api/?target=';

  function proxyUrl(href) {
    try {
      const absolute = new URL(href, originalLocation.href).href;
      return proxyBase + encodeURIComponent(absolute);
    } catch (e) {
      return href;
    }
  }

  // Hook location.assign / replace / href setter
  const locationProxy = new Proxy(originalLocation, {
    set(target, prop, value) {
      if (prop === 'href') {
        return (target.href = proxyUrl(value));
      }
      target[prop] = value;
      return true;
    }
  });
  Object.defineProperty(window, 'location', { value: locationProxy, configurable: false });

  // Hook history.pushState / replaceState
  const origPushState = history.pushState;
  history.pushState = function(state, title, url) {
    if (url) url = proxyUrl(url);
    origPushState.call(history, state, title, url);
    window.top.postMessage({ type: 'iframe-push', url: location.href }, '*');
  };

  const origReplaceState = history.replaceState;
  history.replaceState = function(state, title, url) {
    if (url) url = proxyUrl(url);
    origReplaceState.call(history, state, title, url);
    window.top.postMessage({ type: 'iframe-replace', url: location.href }, '*');
  };

  // Hook open
  const origOpen = window.open;
  window.open = function(url, target, features) {
    return origOpen.call(window, url ? proxyUrl(url) : url, target, features);
  };

  // Intercept fetch and XMLHttpRequest to proxy all outgoing requests
  // (simplified – a real implementation would rewrite URLs)
  // Here we simply ensure that relative URLs are already handled by the SW.
})();