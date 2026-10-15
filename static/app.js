const $ = selector => document.querySelector(selector);
let csrf = '', setupRequired = false, page = 'overview', proxyAddress = '', refreshing = false;
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json', 'X-CSRF-Token':csrf, ...(options.headers || {})}});
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.includes('/auth/')) await bootstrap();
    throw new Error(payload.error || '请求失败，请稍后重试');
  }
  if (payload.csrfToken) csrf = payload.csrfToken;
  return payload;
}
function toast(message) { $('#toast').textContent = message; $('#toast').classList.remove('hidden'); clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').classList.add('hidden'), 3500); }
function errorIn(id, message) { $(id).textContent = message; $(id).classList.toggle('hidden', !message); }
async function bootstrap() {
  try {
    const state = await api('/api/auth/state'); csrf = state.csrfToken; setupRequired = state.setupRequired;
    $('#loading').classList.add('hidden'); $('#auth-view').classList.toggle('hidden', state.authenticated); $('#app-view').classList.toggle('hidden', !state.authenticated);
    $('#auth-kicker').textContent = setupRequired ? '首次使用' : '欢迎回来';
    $('#auth-title').textContent = setupRequired ? '设置管理员' : '登录工作台';
    $('#auth-description').textContent = setupRequired ? '创建管理账号，开始配置你的消息代理。' : '登录后查看代理状态、请求日志与设置。';
    $('#confirm-row').classList.toggle('hidden', !setupRequired); $('#confirm-password').required = setupRequired;
    $('#password').autocomplete = setupRequired ? 'new-password' : 'current-password';
    $('#auth-submit').firstChild.textContent = setupRequired ? '创建账号并进入' : '登录工作台';
    errorIn('#auth-error', '');
    if (state.authenticated) { $('#account-name').textContent = state.username; await refresh(); }
  } catch (error) { $('#loading').textContent = '无法连接管理服务，请检查服务是否正在运行。'; }
}
$('#auth-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#auth-submit'); button.disabled = true; errorIn('#auth-error', '');
  try {
    await api(setupRequired ? '/api/auth/setup' : '/api/auth/login', {method:'POST', body:JSON.stringify({username:$('#username').value.trim(), password:$('#password').value, confirmPassword:$('#confirm-password').value})});
    $('#password').value = ''; $('#confirm-password').value = ''; await bootstrap();
  } catch (error) { errorIn('#auth-error', error.message); } finally { button.disabled = false; }
});
async function logout() { try { await api('/api/auth/logout', {method:'POST'}); await bootstrap(); } catch(error) { toast(error.message); } }
$('#logout').addEventListener('click', logout); $('#mobile-logout').addEventListener('click', logout);
async function changePage(next) {
  page = next;
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === page));
  document.querySelectorAll('.page-section').forEach(section => section.classList.toggle('hidden', section.id !== 'page-' + page));
  $('#page-crumb').textContent = {overview:'代理概览', logs:'代理日志', settings:'代理设置'}[page];
  await refresh();
}
document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => changePage(button.dataset.page)));
document.querySelectorAll('[data-open-settings]').forEach(button => button.addEventListener('click', () => changePage('settings')));
document.querySelectorAll('[data-open-logs]').forEach(button => button.addEventListener('click', () => changePage('logs')));
document.querySelectorAll('.refresh-button').forEach(button => button.addEventListener('click', () => refresh(true)));
function table(records, source) {
  if (!records.length) return '<div class="empty-state"><div class="empty-icon"><svg><use href="#i-empty"/></svg></div><strong>暂无代理请求</strong><p>客户端通过代理调用接口后，请求记录会出现在这里。</p></div>';
  return '<div class="table-wrap"><table><thead><tr><th>请求时间</th><th>方法</th><th>接口</th><th>HTTP 状态</th><th>耗时</th>' + (source ? '<th>来源</th>' : '') + '</tr></thead><tbody>' + records.map(row => {
    const time = new Date(row.time).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
    return `<tr><td>${escapeHTML(time)}</td><td><span class="method-tag">${escapeHTML(row.method)}</span></td><td class="path-cell" title="${escapeHTML(row.path)}"><code>${escapeHTML(row.path)}</code></td><td><span class="http-status ${row.status >= 400 ? 'bad' : ''}">${escapeHTML(row.status)}</span></td><td>${escapeHTML(row.durationMs)} ms</td>${source ? `<td>${escapeHTML(row.client)}</td>` : ''}</tr>`;
  }).join('') + '</tbody></table></div>';
}
function showProxy(proxy) {
  proxyAddress = `http://${location.hostname}:${proxy.port}`; $('#proxy-address').textContent = proxyAddress;
  $('#overview-upload-limit').textContent = `${proxy.maxBodyMiB} MiB`;
  $('#proxy-title').textContent = proxy.running ? '消息代理正在运行' : proxy.enabled ? '代理尚未就绪' : '消息代理已暂停';
  $('#proxy-badge').textContent = proxy.running ? '运行中' : proxy.enabled ? '待处理' : '已暂停';
  $('#proxy-badge').className = 'badge ' + (proxy.running ? 'success' : proxy.enabled ? 'error' : 'neutral');
  $('#proxy-description').textContent = proxy.running ? `正在监听 ${proxy.listenHost}:${proxy.port}，可接收企业微信 API 请求。` : proxy.enabled ? '打开代理设置，检查当前配置和运行环境。' : '需要恢复转发时，可在代理设置中重新启用。';
  $('#service-alert').classList.toggle('hidden', !proxy.error); $('#service-alert').textContent = proxy.error || '';
}
async function refresh(notify = false) {
  if (refreshing || $('#app-view').classList.contains('hidden')) return;
  refreshing = true;
  try {
    if (page === 'overview') {
      const data = await api('/api/overview'); showProxy(data.proxy);
      $('#metric-requests').textContent = data.logs.stats.requests.toLocaleString(); $('#metric-errors').textContent = data.logs.stats.errors.toLocaleString();
      $('#metric-duration').innerHTML = escapeHTML(data.logs.stats.averageMs) + '<em>ms</em>';
      $('#recent-table').innerHTML = table(data.logs.items, false);
    } else if (page === 'logs') {
      const data = await api(`/api/logs?search=${encodeURIComponent($('#log-search').value)}&status=${$('#log-status').value}`);
      $('#logs-table').innerHTML = table(data.items, true); $('#log-count').textContent = `显示 ${data.items.length} 条 · 匹配 ${data.matched} 条`;
    } else {
      const data = await api('/api/settings'); $('#proxy-port').value = data.proxy.port; $('#proxy-enabled').checked = data.proxy.enabled; $('#upload-limit').value = data.proxy.maxBodyMiB; $('#admin-port').textContent = data.adminPort; $('#settings-upload-limit').textContent = `${data.proxy.maxBodyMiB} MiB`;
    }
    if (notify) toast('已刷新');
  } catch (error) { toast(error.message); } finally { refreshing = false; }
}
$('#copy-address').addEventListener('click', async () => { try { await navigator.clipboard.writeText(proxyAddress); toast('代理地址已复制'); } catch(error) { toast('请选中代理地址手动复制'); } });
let searchTimer;
$('#log-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => refresh(), 250); });
$('#log-status').addEventListener('change', () => refresh());
$('#clear-logs').addEventListener('click', () => $('#clear-dialog').showModal());
$('#cancel-clear').addEventListener('click', () => $('#clear-dialog').close());
$('#confirm-clear').addEventListener('click', async () => { try { await api('/api/logs', {method:'DELETE'}); $('#clear-dialog').close(); await refresh(); toast('日志已清空'); } catch(error) { toast(error.message); } });
$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#save-settings'); button.disabled = true; errorIn('#settings-error', '');
  try { const data = await api('/api/settings', {method:'PUT', body:JSON.stringify({port:Number($('#proxy-port').value), enabled:$('#proxy-enabled').checked, maxBodyMiB:Number($('#upload-limit').value)})}); $('#settings-upload-limit').textContent = `${data.proxy.maxBodyMiB} MiB`; toast('代理设置已应用'); }
  catch(error) { errorIn('#settings-error', error.message); } finally { button.disabled = false; }
});
setInterval(() => { if (!document.hidden && page !== 'settings' && (page !== 'logs' || $('#auto-refresh').checked)) refresh(); }, 5000);
bootstrap();
