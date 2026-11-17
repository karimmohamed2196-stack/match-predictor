var V="mp-v1",SHELL=["./","manifest.webmanifest","icon-192.png","icon-512.png"];
self.addEventListener("install",function(e){e.waitUntil(caches.open(V).then(function(c){return Promise.all(SHELL.map(function(u){return c.add(u).catch(function(){})}))}).then(function(){return self.skipWaiting()}))});
self.addEventListener("activate",function(e){e.waitUntil(caches.keys().then(function(K){return Promise.all(K.filter(function(k){return k!==V}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener("fetch",function(e){var r=e.request;if(r.method!=="GET")return;var u=new URL(r.url);if(u.origin!==location.origin)return;
 var net=/data\.json$/.test(u.pathname)||r.mode==="navigate";
 e.respondWith(net?fetch(r).then(function(x){var y=x.clone();caches.open(V).then(function(c){c.put(r,y)});return x}).catch(function(){return caches.match(r).then(function(m){return m||caches.match("./")})}):caches.match(r).then(function(m){return m||fetch(r)}))});
