var V="mp-v3",SHELL=["./","manifest.webmanifest","icon-192.png","icon-512.png"],NAV_TIMEOUT=4000;
function offline(){return new Response("",{status:503,statusText:"offline"})}
function timeout(p,ms){return new Promise(function(res,rej){var t=setTimeout(function(){rej(new Error("timeout"))},ms);p.then(function(x){clearTimeout(t);res(x)},function(e){clearTimeout(t);rej(e)})})}
self.addEventListener("install",function(e){e.waitUntil(caches.open(V).then(function(c){return Promise.all(SHELL.map(function(u){return c.add(u).catch(function(){})}))}).then(function(){return self.skipWaiting()}))});
self.addEventListener("activate",function(e){e.waitUntil(caches.keys().then(function(K){return Promise.all(K.filter(function(k){return k!==V}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener("fetch",function(e){
 var r=e.request;if(r.method!=="GET")return;var u=new URL(r.url);
 // Google Fonts: stale-while-revalidate so the Arabic font works offline
 if(u.hostname==="fonts.googleapis.com"||u.hostname==="fonts.gstatic.com"){
  e.respondWith(caches.open(V).then(function(c){return c.match(r).then(function(m){var f=fetch(r).then(function(x){if(x&&(x.ok||x.type==="opaque"))c.put(r,x.clone());return x}).catch(function(){return m||offline()});return m||f})}));return}
 if(u.origin!==location.origin)return;
 var isData=/data\.json$/.test(u.pathname),isNav=r.mode==="navigate";
 if(isData||isNav){
  // network first; on slow/failed network fall back to the cached copy
  var net=fetch(r,{cache:"no-store"}).then(function(x){if(x.ok){var y=x.clone();caches.open(V).then(function(c){c.put(isNav?"./":r,y)})}return x});
  e.respondWith(timeout(net,isNav?NAV_TIMEOUT:8000).catch(function(){return caches.match(isNav?"./":r).then(function(m){return m||(isNav?caches.match("./"):null)||offline()})}));return}
 e.respondWith(caches.match(r).then(function(m){return m||fetch(r).catch(offline)}));
});
// tapping a notification opens (or focuses) the app
self.addEventListener("notificationclick",function(e){e.notification.close();
 e.waitUntil(self.clients.matchAll({type:"window",includeUncontrolled:true}).then(function(L){for(var i=0;i<L.length;i++){if("focus" in L[i])return L[i].focus()}return self.clients.openWindow("./")}))});
