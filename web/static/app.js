'use strict';
const $=id=>document.getElementById(id);
const inlineQrs=new Map();
const loginPhases=['scan','confirm','finishing','expired'];
function clearInline(n){const item=inlineQrs.get(n);if(!item)return;item.abort?.abort();if(item.url)URL.revokeObjectURL(item.url);item.node.remove();inlineQrs.delete(n);}
function inlineLogin(a){
 const n=a.id;if(!loginPhases.includes(a.phase)){clearInline(n);return;}
 let item=inlineQrs.get(n);
 if(!item){
  const node=document.createElement('section');node.className='inline-login';node.setAttribute('aria-label',`账号 ${n} 扫码登录`);
  node.innerHTML='<div class="inline-login-title"></div><p class="inline-login-message" role="status"></p><div class="inline-qr-stage"><span>正在获取二维码…</span></div><div class="inline-login-actions"><button class="button secondary" data-action="qr-renew">重新生成</button><button class="button secondary" data-action="qr-large">放大二维码</button></div><p class="inline-login-help">使用对应账号的手机 QQ 扫码并确认。同一手机操作时，请用另一台设备显示二维码。</p>';
  for(const button of node.querySelectorAll('button'))button.dataset.id=n;
  document.querySelector(`.account-card[data-account="${n}"]`).querySelector('.card-controls').before(node);
  item={node,url:null,busy:false,key:null,attempt:0};inlineQrs.set(n,item);
 }
 item.node.querySelector('.inline-login-title').textContent=a.phase==='expired'?'登录已失效 · 需要重新扫码':`账号 ${n} · 需要登录`;
 const expired=a.phase==='expired'||(a.qr_expires_at&&a.qr_expires_at*1000<=Date.now());
 item.node.querySelector('.inline-login-message').textContent=expired?'二维码已过期，请点击「重新生成」。':a.phase==='confirm'?'已扫码，请在手机 QQ 上确认。':a.phase==='finishing'?'确认成功，正在保存登录并恢复挂机…':'挂机等待登录，请用手机 QQ 扫描下方二维码。';
 const stage=item.node.querySelector('.inline-qr-stage');
 if(expired){item.attempt++;item.busy=false;item.abort?.abort();if(item.url){URL.revokeObjectURL(item.url);item.url=null;}stage.textContent='二维码已过期';return;}
 const key=a.qr_expires_at||'current';
 if(item.key!==key){item.abort?.abort();item.attempt++;item.busy=false;if(item.url)URL.revokeObjectURL(item.url);item.url=null;item.key=key;stage.textContent='正在获取二维码…';}
 if(!item.url&&!item.busy&&!pending.has(n)&&a.phase!=='finishing')void fetchInline(a,item);
}
async function fetchInline(a,item){
 const n=a.id,attempt=++item.attempt;item.busy=true;const abort=new AbortController();item.abort=abort;
 const timeout=setTimeout(()=>abort.abort(),12000);
 try{
  const response=await fetch(`/api/accounts/${n}/qr?t=${Date.now()}`,{credentials:'same-origin',signal:abort.signal});
  if(response.status===401){showLogin();return;}
  if(!response.ok)throw Error('二维码正在生成，稍后自动重试。');
  const blob=await response.blob();if(inlineQrs.get(n)!==item||item.attempt!==attempt||!loggedIn)return;
  item.url=URL.createObjectURL(blob);const image=new Image();image.alt=`账号 ${n} 登录二维码`;image.src=item.url;item.node.querySelector('.inline-qr-stage').replaceChildren(image);
 }catch(error){if(inlineQrs.get(n)===item&&item.attempt===attempt&&!abort.signal.aborted)item.node.querySelector('.inline-qr-stage').textContent='暂未取得二维码，正在重试…';}
 finally{clearTimeout(timeout);if(item.attempt===attempt)item.busy=false;}
}
async function renewInline(n){
 if(pending.has(n))return;pending.add(n);clearInline(n);paint({accounts});
 try{await api(`/api/accounts/${n}/login`,{method:'POST',body:'{}'});lastStatusSequence=++statusSequence;await loadStatus();}
 catch(error){toast(error.message,true);}finally{pending.delete(n);paint({accounts});}
}
let qrGeneration=0,qrAbort=null,statusSequence=0,lastStatusSequence=0,qrAwaitingFresh=false,qrStatusAfter=Infinity;
let csrf='',loggedIn=false,accounts=[],pending=new Set(),qrAccount=null,logAccount=null,qrObject=null,qrBusy=false,lastQr=0,toastTimer,refreshing=false;
function paintAvatar(card,a,selector='.avatar'){
 const avatar=card.querySelector(selector),key=String(a.id);if(avatar.dataset.phase&&avatar.dataset.phase!==a.phase&&['online','verified'].includes(a.phase))delete avatar.dataset.avatarId;avatar.dataset.phase=a.phase;
 if(avatar.dataset.avatarId===key)return;
 avatar.dataset.avatarId=key;avatar.textContent=key.padStart(2,'0');
 const img=document.createElement('img');img.alt='';img.loading='lazy';img.addEventListener('error',()=>img.remove(),{once:true});img.src=`/api/accounts/${key}/avatar`;avatar.append(img);
}
const labels={online:'在线挂机',verified:'连接游戏中',scan:'等待扫码',confirm:'等待手机确认',finishing:'正在完成登录',expired:'二维码已过期',reconnecting:'正在重连',unknown:'运行中',stopped:'已停止'};
let notificationBaseline=null,notificationEnabled=localStorage.getItem('tankstorm-notifications')==='on';
const notificationCooldown=new Map();
function notificationSupported(){return typeof window.Notification==='function';}
function updateNotificationControls(){
 const toggle=$('notification-toggle'),test=$('notification-test');
 const supported=notificationSupported();const permission=supported?Notification.permission:'unsupported';
 toggle.checked=notificationEnabled&&permission==='granted';toggle.disabled=!supported;
 test.disabled=!toggle.checked;
 $('notification-status').textContent=!supported?'浏览器不支持通知':permission==='denied'?'通知被浏览器阻止，请在网站设置中允许':toggle.checked?'已开启':'已关闭';
}
async function sendBrowserNotice(title,body,tag){
 if(!notificationEnabled||!notificationSupported()||Notification.permission!=='granted')return false;
 const options={body,tag,icon:'/static/icon.svg'};
 if('serviceWorker' in navigator){
  try{const registration=await navigator.serviceWorker.register('/static/notification-worker.js');if(!registration.active){const worker=registration.installing||registration.waiting;if(!worker)throw Error('worker unavailable');await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('timeout')),8000);const check=()=>{if(worker.state==='activated'){clearTimeout(timer);resolve();}else if(worker.state==='redundant'){clearTimeout(timer);reject(Error('worker failed'));}};worker.addEventListener('statechange',check);check();});}await registration.showNotification(title,options);return true;}catch{}
 }
 try{new Notification(title,options);return true;}catch{toast('此浏览器无法显示通知，请尝试手机 Chrome 并检查系统通知设置',true);return false;}
}
function checkAccountNotifications(values){
 const next=new Map(values.map(a=>[a.id,a]));
 if(notificationBaseline&&notificationEnabled){
  for(const a of values){const previous=notificationBaseline.get(a.id);if(!previous)continue;
   const wasHealthy=previous.phase==='online'||previous.phase==='verified';
   const nowProblem=['reconnecting','scan','confirm','finishing','expired'].includes(a.phase);
   if(wasHealthy&&nowProblem&&!pending.has(a.id)){
    const now=Date.now(),last=notificationCooldown.get(a.id)||0;
    if(now-last>=300000){const message=['scan','confirm','finishing','expired'].includes(a.phase)?'登录需要重新确认，请打开网页扫码。':'连接已断开，正在尝试重连。';notificationCooldown.set(a.id,now);void sendBrowserNotice(`${a.name} · 账号异常`,message,`account-${a.id}`).then(ok=>{if(!ok&&notificationCooldown.get(a.id)===now)notificationCooldown.delete(a.id);});}
   }
  }
 }
 notificationBaseline=next;
}
function toast(message,failure=false){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').classList.toggle('failure',failure);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
async function api(path,options={}){const headers={...options.headers};if(options.method==='POST'){headers['Content-Type']='application/json';if(csrf)headers['X-CSRF-Token']=csrf;}const response=await fetch(path,{...options,headers,credentials:'same-origin',signal:AbortSignal.timeout(45000)});let data;try{data=await response.json();}catch{throw Error('服务器返回异常，请稍后重试');}if(!response.ok){if(response.status===401&&path!='/api/login'){showLogin();document.getElementById('login-error').textContent='管理登录已过期，请重新输入管理密码。服务器挂机不受影响。';}throw Error(data.error||'操作未完成');}return data;}
function showLogin(){for(const n of inlineQrs.keys())clearInline(n);notificationBaseline=null;loggedIn=false;csrf='';$('dashboard').hidden=true;$('login-screen').hidden=false;document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());}
async function showDashboard(token){csrf=token;loggedIn=true;$('login-screen').hidden=true;$('dashboard').hidden=false;$('password').value='';await refresh();}
function duration(seconds){const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;}
function connection(ok){$('connection').classList.toggle('offline',!ok);$('connection').lastElementChild.textContent=ok?'服务器已连接':'连接中断';}
function syncCards(values){const ids=new Set(values.map(a=>a.id));for(const card of document.querySelectorAll('.account-card')){card.hidden=!ids.has(card.dataset.account);if(card.hidden){clearInline(card.dataset.account);delete card.querySelector('.avatar').dataset.avatarId;}}for(const event of document.querySelectorAll('[data-event-account]')){event.hidden=!ids.has(event.dataset.eventAccount);if(event.hidden)delete event.querySelector('.activity-number').dataset.avatarId;}
 for(const a of values){if(document.querySelector(`.account-card[data-account="${a.id}"]`))continue;const original=document.querySelector('.account-card');const card=original.cloneNode(true);card.querySelector('.inline-login')?.remove();card.hidden=false;card.dataset.account=a.id;delete card.querySelector('.avatar').dataset.avatarId;card.querySelector('.avatar').textContent=String(a.id).padStart(2,'0');card.querySelector('h2').textContent=a.name;
 for(const node of card.querySelectorAll('[id]'))node.id=node.id.replace(/-1$/,`-${a.id}`);for(const button of card.querySelectorAll('[data-id]'))button.dataset.id=a.id;$('accounts-list').append(card);
 const activity=document.querySelector('[data-event-account="1"]').cloneNode(true);activity.dataset.eventAccount=a.id;delete activity.querySelector('.activity-number').dataset.avatarId;activity.querySelector('.activity-number').textContent=String(a.id).padStart(2,'0');activity.querySelector('div').querySelector('span').textContent=a.name;activity.querySelector('p').id=`event-${a.id}`;document.querySelector('.activity-section').append(activity);
 }
 $('account-count').textContent=values.length;$('online-total').textContent=`/ ${values.length} 个账号运行中`;
}
function bytes(value){return `${(value/1073741824).toFixed(1)} GB`;}
function health(server){if(!server)return;$('cpu-value').textContent=server.cpu_percent===null?'采样中':`${server.cpu_percent.toFixed(1)}%`;$('cpu-detail').textContent=`1 分钟平均负载 ${server.load_1m}`;$('server-cores').textContent=`${server.cpu_cores} 核 CPU · 实时更新`;$('cpu-bar').style.width=`${server.cpu_percent||0}%`;
 $('memory-value').textContent=`${server.memory_percent.toFixed(1)}%`;$('memory-detail').textContent=`${bytes(server.memory_used)} / ${bytes(server.memory_total)}`;$('memory-bar').style.width=`${server.memory_percent}%`;$('memory-tile').classList.toggle('warning',server.memory_percent>85);
 $('disk-value').textContent=`${server.disk_percent.toFixed(1)}%`;$('disk-detail').textContent=`${bytes(server.disk_used)} / ${bytes(server.disk_total)}`;$('disk-bar').style.width=`${server.disk_percent}%`;
 const days=Math.floor(server.uptime/86400),hours=Math.floor(server.uptime%86400/3600);$('server-uptime').textContent=days?`${days}天 ${hours}时`:`${hours}时 ${Math.floor(server.uptime%3600/60)}分`;
}
async function loadStatus(){const sequence=++statusSequence;const data=await api('/api/status');if(sequence<lastStatusSequence)return;lastStatusSequence=sequence;if(qrAwaitingFresh&&sequence>=qrStatusAfter)qrAwaitingFresh=false;checkAccountNotifications(data.accounts);paint(data);return data;}
function paint(data){syncCards(data.accounts);health(data.server);accounts=data.accounts;$('online-count').textContent=accounts.filter(a=>a.state==='active').length;
 for(const a of accounts){inlineLogin(a);const n=a.id,needs=['scan','confirm','finishing','expired'].includes(a.phase),running=a.state==='active';const card=document.querySelector(`.account-card[data-account="${n}"]`);paintAvatar(card,a);card.querySelector('h2').textContent=a.name;card.querySelector('.account-identity p').textContent=Number.isInteger(a.region)?`${a.region} 区`:'区服未知';const stop=running||a.state==='login';card.querySelector('[data-action="start"]').hidden=stop;card.querySelector('[data-action="stop"]').hidden=!stop;document.querySelector(`[data-event-account="${n}"] div>span`).textContent=a.name;const badge=$(`badge-${n}`);badge.textContent=labels[a.phase]||'检查状态';badge.className=`badge ${needs?'warning':running?'':'stopped'}`;$(`uptime-${n}`).textContent=duration(running?a.uptime:0);$(`done-${n}`).textContent=a.completed;$(`total-${n}`).textContent=` / ${a.total}`;$(`progress-${n}`).style.width=`${a.total?Math.min(100,a.completed/a.total*100):0}%`;
 const descriptions={online:'游戏已连接，服务器持续保活。',verified:'QQ 登录有效，正在连接游戏。',scan:'需要手机 QQ 扫码，点击下方「扫码登录」。',confirm:'已经扫码，请在手机 QQ 上确认登录。',finishing:'手机确认成功，正在保存登录状态。',expired:'二维码已过期，请重新生成。',reconnecting:'连接已断开，服务器正在自动重连。',unknown:'服务运行中，正在获取游戏状态。',stopped:'账号已停止，点击「启动」恢复挂机。'};
 $(`phase-${n}`).textContent=descriptions[a.phase]||'正在检查账号状态…';$(`event-${n}`).textContent=a.last_event.replace(/^\d{4}-\d\d-\d\d\s/,'');
 const eventCard=document.querySelector(`[data-event-account="${n}"]`);paintAvatar(eventCard,a,'.activity-number');const eventState=needs?'warning':a.phase==='online'?'online':a.state==='active'?'working':'stopped';eventCard.dataset.state=eventState;
 let stateText=eventCard.querySelector('.activity-state');if(!stateText){stateText=document.createElement('span');stateText.className='activity-state';eventCard.querySelector('div').append(stateText);}stateText.textContent=labels[a.phase]||'检查状态';
 for(const button of document.querySelectorAll(`button[data-id="${n}"]`)){const action=button.dataset.action;button.disabled=pending.has(n)||(action==='start'&&(running||a.state==='login'))||(action==='stop'&&!running&&a.state!=='login');}
 }
 const waiting=accounts.filter(a=>loginPhases.includes(a.phase));
 let alert=$('login-alert');if(!alert){alert=document.createElement('button');alert.id='login-alert';alert.className='login-alert';document.querySelector('.accounts-heading').before(alert);alert.addEventListener('click',()=>document.querySelector('.inline-login')?.scrollIntoView({block:'center',behavior:'smooth'}));}
 alert.hidden=!waiting.length;alert.textContent=`${waiting.length} 个账号需要登录 · 点击查看二维码`;
 $('last-update').textContent=`更新于 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})}`;
}
async function refresh(){if(!loggedIn||refreshing)return;refreshing=true;try{await loadStatus();connection(true);if($('qr-dialog').open)await refreshQr();if($('logs-dialog').open)await refreshLogs();}catch(error){connection(false);}finally{refreshing=false;}}
function confirmation(title,message){$('confirm-title').textContent=title;$('confirm-text').textContent=message;const dialog=$('confirm-dialog');dialog.showModal();return new Promise(resolve=>{const done=answer=>{dialog.close();$('accept-confirm').onclick=null;$('cancel-confirm').onclick=null;dialog.oncancel=null;resolve(answer);};$('accept-confirm').onclick=()=>done(true);$('cancel-confirm').onclick=()=>done(false);dialog.oncancel=event=>{event.preventDefault();done(false);};});}
function askName(account){const dialog=$('name-dialog'),input=$('account-name-input');$('name-title').textContent=`修改账号 ${account.id} 的名称`;input.value=account.name;$('name-error').textContent='';dialog.showModal();input.focus();input.select();return new Promise(resolve=>{const done=value=>{dialog.close();$('save-name').onclick=null;$('cancel-name').onclick=null;dialog.oncancel=null;resolve(value);};$('cancel-name').onclick=()=>done(null);dialog.oncancel=e=>{e.preventDefault();done(null);};$('save-name').onclick=()=>{const value=input.value.trim();if(!value||Array.from(value).length>32){$('name-error').textContent='请输入 1 至 32 个字符';return;}done(value);};});}
async function changeAccount(id,action,body){pending.add(id);paint({accounts});try{await api(`/api/accounts/${id}/${action}`,{method:'POST',body:JSON.stringify(body||{})});lastStatusSequence=++statusSequence;await loadStatus();toast(action==='delete'?'账号已删除，数据已备份':'账号名称已更新');}catch(error){toast(error.message,true);}finally{pending.delete(id);paint({accounts});}}
async function operate(n,action){pending.add(String(n));paint({accounts});try{await api(`/api/accounts/${n}/${action}`,{method:'POST',body:'{}'});toast(action==='start'?`账号 ${n} 已启动`:`账号 ${n} 已停止`);lastStatusSequence=++statusSequence;await loadStatus();}catch(error){toast(error.message,true);}finally{pending.delete(String(n));paint({accounts});}}
function clearQr(){if(qrObject){URL.revokeObjectURL(qrObject);qrObject=null;}lastQr=0;}
function resetQrAttempt(){qrGeneration++;if(qrAbort)qrAbort.abort();qrAbort=null;qrBusy=false;clearQr();}
function qrLoading(){resetQrAttempt();$('qr-stage').innerHTML='<div class="spinner"></div><p>正在生成新二维码…</p>';$('qr-message').textContent='请稍候，二维码生成后自动显示';}
async function openQr(n,force=false){const a=accounts.find(a=>a.id===String(n));const reusable=a&&['scan','confirm','finishing'].includes(a.phase);if(!force&&!reusable){if(!await confirmation(`重新登录账号 ${n}？`,'此账号会暂停运行。扫码确认后自动恢复，另一个账号继续运行。'))return;}
 qrAwaitingFresh=force||!reusable;qrAccount=String(n);$('qr-title').textContent=`账号 ${n} · 扫码登录`;qrStatusAfter=Infinity;qrLoading();const attempt=qrGeneration;if(!$('qr-dialog').open)$('qr-dialog').showModal();
 if(force||!reusable){pending.add(String(n));$('refresh-qr').disabled=true;try{await api(`/api/accounts/${n}/login`,{method:'POST',body:'{}'});}catch(error){$('qr-message').textContent=error.message;toast(error.message,true);return;}finally{pending.delete(String(n));$('refresh-qr').disabled=false;}}
 if(attempt!==qrGeneration||String(n)!==qrAccount||!$('qr-dialog').open)return;qrStatusAfter=statusSequence+1;try{await loadStatus();await refreshQr();}catch(error){$('qr-message').textContent='连接暂时中断，恢复后会自动显示二维码。';}
}
async function refreshQr(){if(qrBusy||qrAwaitingFresh||!qrAccount||!$('qr-dialog').open)return;const a=accounts.find(a=>a.id===qrAccount);if(!a)return;
 if(a.state==='active'&&['online','verified'].includes(a.phase)){resetQrAttempt();$('qr-stage').innerHTML='<svg class="success-icon"><use href="#check"/></svg><p>登录成功</p>';$('qr-message').textContent='服务器已恢复挂机，可以关闭此窗口。';return;}
 if(a.phase==='expired'||(a.state!=='login'&&a.state!=='active')){$('qr-message').textContent='二维码已过期或登录已停止，请重新生成。';return;}
 $('qr-message').textContent=a.phase==='confirm'?'已扫码，请在手机 QQ 上确认':a.phase==='finishing'?'手机确认成功，正在完成登录…':'请用对应账号的手机 QQ 扫码';
 if(qrObject&&Date.now()-lastQr<12000)return;qrBusy=true;const slot=qrAccount,generation=qrGeneration;const controller=new AbortController();qrAbort=controller;const timeout=setTimeout(()=>controller.abort(),12000);
 try{const response=await fetch(`/api/accounts/${slot}/qr?t=${Date.now()}`,{credentials:'same-origin',signal:controller.signal});if(!response.ok)return;const blob=await response.blob();if(generation!==qrGeneration||slot!==qrAccount||!$('qr-dialog').open)return;clearQr();qrObject=URL.createObjectURL(blob);const image=new Image();image.alt=`账号 ${slot} 登录二维码`;image.src=qrObject;$('qr-stage').replaceChildren(image);lastQr=Date.now();}catch{}finally{clearTimeout(timeout);if(generation===qrGeneration){qrBusy=false;qrAbort=null;}}
}
async function refreshLogs(){if(!logAccount)return;const slot=logAccount;try{const data=await api(`/api/accounts/${slot}/logs`);if(logAccount!==slot)return;const content=data.lines.join('\n')||'暂无运行日志';if($('logs-content').textContent!==content){$('logs-content').textContent=content;if($('auto-scroll').checked)$('logs-content').scrollTop=$('logs-content').scrollHeight;}$('logs-updated').textContent=`更新于 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})}`;}catch(error){$('logs-updated').textContent=error.message;}}
$('add-account').addEventListener('click',async()=>{if(!await confirmation('添加一个新账号？','新账号使用独立配置，不会复制现有账号的登录信息。创建后，请点击该账号的「扫码登录」。'))return;const button=$('add-account');button.disabled=true;try{const result=await api('/api/accounts',{method:'POST',body:'{}'});await loadStatus();toast(`账号 ${result.account} 已创建，请单独扫码登录`);document.querySelector(`.account-card[data-account="${result.account}"]`).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});}catch(error){toast(error.message,true);}finally{button.disabled=false;}});
$('login-form').addEventListener('submit',async event=>{event.preventDefault();$('login-submit').disabled=true;$('login-error').textContent='';try{const data=await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value.trim(),password:$('password').value})});await showDashboard(data.csrf);}catch(error){$('login-error').textContent=error.message;}finally{$('login-submit').disabled=false;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST',body:'{}'});showLogin();}catch(error){toast(error.message,true);}});
$('notification-toggle').addEventListener('change',async event=>{
 if(!event.target.checked){notificationEnabled=false;localStorage.setItem('tankstorm-notifications','off');updateNotificationControls();return;}
 if(!notificationSupported()){notificationEnabled=false;updateNotificationControls();return;}
 let result=Notification.permission;try{if(result==='default')result=await Notification.requestPermission();}catch{result='denied';}
 notificationEnabled=result==='granted';localStorage.setItem('tankstorm-notifications',notificationEnabled?'on':'off');notificationBaseline=null;updateNotificationControls();
 if(!notificationEnabled)toast('请在浏览器网站设置中允许通知',true);
});
$('notification-test').addEventListener('click',async()=>{if(await sendBrowserNotice('坦克风暴 · 测试通知','通知已开启，账号掉线时会提醒你。','tankstorm-test'))toast('已请求显示测试通知');});
updateNotificationControls();
document.addEventListener('click',async event=>{const close=event.target.closest('[data-close]');if(close){$(close.dataset.close).close();return;}const button=event.target.closest('button[data-action]');if(!button||button.disabled)return;const {id,action}=button.dataset;
 const menu=button.closest('.account-menu');if(menu)menu.open=false;
 if(action==='logs'){logAccount=id;$('logs-title').textContent=`账号 ${id} · 运行日志`;$('logs-content').textContent='正在读取…';$('logs-dialog').showModal();await refreshLogs();}
 else if(action==='rename'){const a=accounts.find(x=>x.id===id);if(!a)return;const name=await askName(a);if(name!==null)await changeAccount(id,'rename',{name});}
 else if(action==='delete'){const a=accounts.find(x=>x.id===id);if(a&&await confirmation(`删除「${a.name}」？`,'将停止该账号并移除网页卡片。登录信息、配置和日志会备份到服务器，其他账号不受影响。'))await changeAccount(id,'delete');}
 else if(action==='qr-renew')await renewInline(id);
 else if(action==='qr-large')await openQr(id);
 else if(action==='login'){
  const a=accounts.find(a=>a.id===id);
  if(a&&['scan','confirm','finishing'].includes(a.phase))document.querySelector(`.account-card[data-account="${id}"] .inline-login`)?.scrollIntoView({block:'center',behavior:'smooth'});
  else if(await confirmation(`登录账号 ${id}？`,'将为这个账号生成二维码，显示在账号卡片内。确认登录后自动恢复挂机，其他账号不受影响。'))await renewInline(id);
 }
 else if(action==='stop'){if(await confirmation(`停止账号 ${id}？`,'停止后不再执行保活和日常任务。另一个账号不受影响，可随时手动启动。'))await operate(id,action);}
 else await operate(id,action);
});
$('refresh-qr').addEventListener('click',()=>openQr(qrAccount,true));$('refresh-logs').addEventListener('click',refreshLogs);
$('qr-dialog').addEventListener('close',()=>{qrAccount=null;resetQrAttempt();});$('logs-dialog').addEventListener('close',()=>logAccount=null);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(loggedIn)refresh();},3000);
(async()=>{try{const data=await api('/api/session');await showDashboard(data.csrf);}catch{showLogin();}})();


