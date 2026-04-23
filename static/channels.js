window._channelsAvailable = true

let _channelsState = null
let _channelsRefreshTimer = null
let _weixinQrSource = null
let _gatewayActionState = { busy: false, action: '' }

const _CHANNELS_POLL_MS = 15000
const _LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

let _weixinQrState = _newWeixinQrState()

function _newWeixinQrState(keepDisclosure) {
  return {
    active: false,
    disclosureAccepted: !!keepDisclosure,
    pollToken: '',
    qrcodeUrl: '',
    status: 'idle',
    message: '',
    refreshes: 0,
  }
}

function _channelsText(key, fallback, ...args) {
  const resolved = typeof t === 'function' ? t(key, ...args) : key
  return resolved && resolved !== key ? resolved : (fallback || key)
}

function _gatewayActionLabel(action) {
  if (_gatewayActionState.busy && _gatewayActionState.action === action) {
    return action === 'start'
      ? _channelsText('channels_gateway_starting', 'Starting...')
      : _channelsText('channels_gateway_restarting', 'Restarting...')
  }
  return action === 'start'
    ? _channelsText('channels_gateway_start', 'Start')
    : _channelsText('channels_gateway_restart', 'Restart')
}

function _channelsProfileName() {
  return ((_channelsState && _channelsState.profile && _channelsState.profile.name) || S.activeProfile || 'default')
}

function _weixinRiskAckKey(profileName) {
  return `hermes.weixin.ilink_risk_acknowledged:${profileName || 'default'}`
}

function _loadWeixinRiskAck(profileName) {
  try {
    return localStorage.getItem(_weixinRiskAckKey(profileName || _channelsProfileName())) === '1'
  } catch (_) {
    return false
  }
}

function _storeWeixinRiskAck(profileName, acknowledged) {
  try {
    if (acknowledged) localStorage.setItem(_weixinRiskAckKey(profileName || _channelsProfileName()), '1')
    else localStorage.removeItem(_weixinRiskAckKey(profileName || _channelsProfileName()))
  } catch (_) {}
}

function _syncWeixinRiskAck(profileName) {
  _weixinQrState.disclosureAccepted = _loadWeixinRiskAck(profileName)
}

function _channelsNav() {
  return document.querySelector('.nav-tab[data-panel="channels"]')
}

function _channelsPanelActive() {
  return _currentPanel === 'channels'
}

function _channelsRemoteHost() {
  return !_LOOPBACK_HOSTS.has((location.hostname || '').toLowerCase())
}

function _channelsParseEvent(event) {
  try {
    const parsed = JSON.parse(event.data || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch (_) {
    return {}
  }
}

function _clearChannelsTimer() {
  if (_channelsRefreshTimer) {
    clearInterval(_channelsRefreshTimer)
    _channelsRefreshTimer = null
  }
}

function _resetWeixinQrState() {
  _weixinQrState = _newWeixinQrState(_loadWeixinRiskAck())
}

function setChannelsAvailability(enabled) {
  window._channelsAvailable = enabled !== false
  const tab = _channelsNav()
  if (tab) tab.classList.toggle('is-disabled', !window._channelsAvailable)
  if (!window._channelsAvailable) {
    stopChannelsPolling()
    if (_channelsPanelActive()) _renderChannelsLocked()
  }
}

async function refreshChannelsAvailability(enabled) {
  if (typeof enabled === 'boolean') {
    setChannelsAvailability(enabled)
    return window._channelsAvailable
  }
  try {
    const auth = await api('/api/auth/status')
    setChannelsAvailability(!!auth.auth_enabled)
  } catch (_) {
    setChannelsAvailability(false)
  }
  return window._channelsAvailable
}

function stopChannelsPolling() {
  _clearChannelsTimer()
  _closeWeixinQrStream()
}

function resetChannelsPanelState() {
  stopChannelsPolling()
  _channelsState = null
  _gatewayActionState = { busy: false, action: '' }
  _resetWeixinQrState()
  const gateway = $('channelsGateway')
  const cards = $('channelsCards')
  if (gateway) gateway.innerHTML = `<span>${esc(t('loading'))}</span>`
  if (cards) cards.innerHTML = ''
}

function _scheduleChannelsPolling() {
  _clearChannelsTimer()
  if (!_channelsPanelActive() || window._channelsAvailable === false) return
  _channelsRefreshTimer = setInterval(() => {
    if (document.hidden || !_channelsPanelActive()) return
    loadChannelsPanel(true)
  }, _CHANNELS_POLL_MS)
}

async function loadChannelsPanel(silent) {
  const cards = $('channelsCards')
  if (!cards) return null

  if (window._channelsAvailable === false) {
    _renderChannelsLocked()
    return null
  }

  if (!silent) {
    cards.innerHTML = `<div class="channels-lock"><div class="channels-lock-title">${esc(_channelsText('loading', 'Loading...'))}</div></div>`
  }

  try {
    const data = await api('/api/channels')
    _channelsState = data
    _syncWeixinRiskAck(data && data.profile ? data.profile.name : null)
    setChannelsAvailability(true)
    _renderChannelsPanel(data)
    _scheduleChannelsPolling()
    return data
  } catch (err) {
    if ((err.message || '').includes('channels_require_auth_enabled')) {
      setChannelsAvailability(false)
      _renderChannelsLocked()
      return null
    }
    cards.innerHTML = `<div class="channels-lock"><div class="channels-lock-title">${esc(_channelsText('error_prefix', 'Error: '))}${esc(err.message || _channelsText('channels_unknown_error', 'Unknown error.'))}</div></div>`
    return null
  }
}

function _renderChannelsLocked() {
  const line = $('channelsProfileLine')
  if (line && !_channelsState?.profile) line.textContent = S.activeProfile || 'default'
  const warning = $('channelsHostWarning')
  if (warning) warning.style.display = 'none'
  const gateway = $('channelsGateway')
  if (gateway) gateway.innerHTML = ''
  const cards = $('channelsCards')
  if (!cards) return
  cards.innerHTML = `
    <div class="channels-lock">
      <div class="channels-lock-title">${esc(_channelsText('channels_requires_auth', 'Channels require auth'))}</div>
      <div class="channels-lock-body">${esc(_channelsText('channels_requires_auth_body', 'Enable password auth in Settings before editing channel credentials or starting QR login flows.'))}</div>
    </div>
  `
}

function _formatChannelTime(raw) {
  if (!raw && raw !== 0) return _channelsText('not_available', 'N/A')
  const date = typeof raw === 'number' ? new Date(raw * 1000) : new Date(raw)
  return Number.isNaN(date.getTime()) ? String(raw) : date.toLocaleString()
}

function _formatActiveAgents(value) {
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return String(value.length)
  if (value && typeof value === 'object') return String(Object.keys(value).length)
  return _channelsText('not_available', 'N/A')
}

function _gatewayControlReason(control) {
  if (!control) {
    return _channelsText('channels_gateway_control_unavailable', 'Gateway control is unavailable for this profile.')
  }
  if (control.reason_key) {
    return _channelsText(control.reason_key, control.reason || '')
  }
  return control.reason || _channelsText('channels_gateway_control_unavailable', 'Gateway control is unavailable for this profile.')
}

function _gatewayScopeText(scope) {
  if (scope === 'system') return _channelsText('channels_gateway_scope_system', 'System')
  if (scope === 'user') return _channelsText('channels_gateway_scope_user', 'User')
  if (scope === 'container') return _channelsText('channels_gateway_scope_container', 'Container')
  return _channelsText('channels_not_available', 'Not available')
}

function _gatewayHintText(control, running) {
  if (!control) return _gatewayControlReason(control)
  if (!control.available) return _gatewayControlReason(control)
  return running
    ? _channelsText('channels_gateway_control_hint', 'WebUI directly calls hermes gateway restart for the current profile. Actual behavior follows the Hermes CLI on this platform.')
    : _channelsText('channels_gateway_start_hint', 'WebUI directly calls hermes gateway start for the current profile. Actual behavior follows the Hermes CLI on this platform.')
}

function _renderGatewayStatus(gateway) {
  const box = $('channelsGateway')
  if (!box) return
  const running = !!(gateway && gateway.running)
  const control = gateway && gateway.control ? gateway.control : {}
  const controlsBusy = !!_gatewayActionState.busy
  const actionAvailable = !!control.available
  const stateLabel = running
    ? _channelsText('channels_gateway_running', 'Gateway running')
    : _channelsText('channels_gateway_stopped', 'Gateway stopped')
  const updated = gateway && (gateway.updated_at || gateway.state_mtime)
  const profileName = (_channelsState && _channelsState.profile && _channelsState.profile.name) || S.activeProfile || 'default'
  const platforms = gateway && Array.isArray(gateway.platforms) && gateway.platforms.length
    ? gateway.platforms.join(', ')
    : _channelsText('channels_not_available', 'Not available')
  const manager = control.manager || _channelsText('channels_not_available', 'Not available')
  const scope = _gatewayScopeText(control.scope)
  const serviceInstalled = control.service_installed === true
  const serviceStatus = serviceInstalled
    ? _channelsText('channels_gateway_service_installed', 'Installed')
    : _channelsText('channels_gateway_service_missing', 'Not installed')
  const servicePath = control.service_path || _channelsText('channels_not_available', 'Not available')
  const servicePathLabel = serviceInstalled
    ? _channelsText('channels_gateway_service_path', 'Service path')
    : _channelsText('channels_gateway_service_expected_path', 'Expected service path')
  const disabledReason = !actionAvailable ? ` title="${esc(_gatewayControlReason(control))}"` : ''

  box.innerHTML = `
    <div class="channels-gateway-line">
      <div class="channels-status ${running ? 'ok' : 'idle'}">${esc(stateLabel)}</div>
      <div class="channels-gateway-actions">
        ${running
          ? `<button class="cron-btn" type="button" onclick="restartGateway()" ${(!actionAvailable || controlsBusy) ? 'disabled' : ''}${disabledReason}>${esc(_gatewayActionLabel('restart'))}</button>`
          : `<button class="cron-btn run" type="button" onclick="startGateway()" ${(!actionAvailable || controlsBusy) ? 'disabled' : ''}${disabledReason}>${esc(_gatewayActionLabel('start'))}</button>`
        }
        <button class="channels-gateway-copy" type="button" onclick="copyChannelsHome()">${esc(_channelsText('channels_gateway_copy_home', 'Copy HERMES_HOME'))}</button>
      </div>
    </div>
    <div class="channels-gateway-list">
      <div><strong>${esc(_channelsText('channels_gateway_profile', 'Profile'))}</strong> <code>${esc(profileName)}</code></div>
      <div><strong>${esc(_channelsText('channels_gateway_home', 'HERMES_HOME'))}</strong> <code>${esc((gateway && gateway.hermes_home) || '')}</code></div>
      <div><strong>${esc(_channelsText('channels_gateway_pid', 'PID'))}</strong> <code>${esc(gateway && gateway.pid ? String(gateway.pid) : _channelsText('not_available', 'N/A'))}</code></div>
      <div><strong>${esc(_channelsText('channels_gateway_manager', 'Service manager'))}</strong> ${esc(manager)}</div>
      <div><strong>${esc(_channelsText('channels_gateway_scope', 'Scope'))}</strong> ${esc(scope)}</div>
      <div><strong>${esc(_channelsText('channels_gateway_service_status', 'Service status'))}</strong> ${esc(serviceStatus)}</div>
      <div><strong>${esc(servicePathLabel)}</strong> <code>${esc(servicePath)}</code></div>
      <div><strong>${esc(_channelsText('channels_gateway_platforms', 'Platforms'))}</strong> ${esc(platforms)}</div>
      <div><strong>${esc(_channelsText('channels_gateway_agents', 'Active agents'))}</strong> ${esc(_formatActiveAgents(gateway && gateway.active_agents))}</div>
      <div><strong>${esc(_channelsText('channels_gateway_updated_label', 'Updated'))}</strong> ${esc(_formatChannelTime(updated))}</div>
      <div>${esc(_gatewayHintText(control, running))}</div>
    </div>
  `
}

function _renderChannelsPanel(data) {
  const profile = data && data.profile ? data.profile : {}
  const line = $('channelsProfileLine')
  if (line) {
    const name = profile.name || 'default'
    const home = profile.hermes_home || ''
    line.textContent = home ? `${name} · ${home}` : name
  }

  const warning = $('channelsHostWarning')
  if (warning) {
    if (_channelsRemoteHost()) {
      warning.textContent = _channelsText(
        'channels_remote_warning',
        'You are editing channel credentials from a remote browser session. Keep auth enabled and only scan QR codes on trusted devices.',
        location.host
      )
      warning.style.display = ''
    } else {
      warning.style.display = 'none'
      warning.textContent = ''
    }
  }

  _renderGatewayStatus(data.gateway || {})

  const cards = $('channelsCards')
  if (!cards) return
  const channels = Array.isArray(data.channels) ? data.channels : []
  cards.innerHTML = channels.length
    ? channels.map(channel => _renderChannelCard(channel)).join('')
    : `<div class="channels-lock"><div class="channels-lock-title">${esc(_channelsText('channels_not_available', 'Not available'))}</div></div>`

  _renderWeixinQrCanvas()
}

function _renderChannelCard(channel) {
  const status = channel && channel.status ? channel.status : {}
  const statusText = status.key
    ? _channelsText(status.key, status.text || '')
    : (status.text || _channelsText('channels_status_not_configured', 'Not configured'))
  const warning = channel.warning
    ? `<div class="channels-card-warning">${esc(_channelsText(channel.warning_key, channel.warning))}</div>`
    : ''
  return `
    <section class="channels-card" data-channel-key="${esc(channel.key)}">
      <div class="channels-card-head">
        <div>
          <div class="channels-card-title">${esc(channel.title || channel.key)}</div>
          <div class="channels-card-desc">${esc(channel.description || '')}</div>
        </div>
        <div class="channels-status ${(status.level || 'idle')}">${esc(statusText)}</div>
      </div>
      ${warning}
      <form class="channels-card-form" id="channelsForm-${esc(channel.key)}" onsubmit="event.preventDefault(); saveChannel('${esc(channel.key)}')">
        ${(channel.schema || []).map(field => _renderChannelField(channel, field)).join('')}
      </form>
      ${_renderChannelMeta(channel)}
      ${channel.key === 'weixin' ? _renderWeixinBlock(channel) : ''}
      <div class="channels-card-actions">
        <button class="cron-btn run" type="button" onclick="saveChannel('${esc(channel.key)}')">${esc(_channelsText('save', 'Save'))}</button>
        ${channel.supports_test ? `<button class="cron-btn" type="button" onclick="testChannel('${esc(channel.key)}')">${esc(_channelsText('channels_test_action', 'Test'))}</button>` : ''}
        <button class="cron-btn" type="button" onclick="deleteChannel('${esc(channel.key)}')">${esc(_channelsText('delete_title', 'Delete'))}</button>
      </div>
    </section>
  `
}

function _renderChannelField(channel, field) {
  const value = channel && channel.values && channel.values[field.name] != null
    ? String(channel.values[field.name])
    : String(field.default || '')
  const label = _channelsText(field.label_key, field.label || field.name)
  const placeholder = field.placeholder_key
    ? _channelsText(field.placeholder_key, field.placeholder || '')
    : (field.placeholder || '')
  const id = `channels-${channel.key}-${field.name}`
  if (field.type === 'select') {
    const current = value || field.default || ''
    const options = (field.options || []).map(option => {
      const selected = current === String(option.value) ? ' selected' : ''
      return `<option value="${esc(option.value)}"${selected}>${esc(option.label)}</option>`
    }).join('')
    return `
      <div class="channels-field">
        <label for="${esc(id)}">${esc(label)}</label>
        <select id="${esc(id)}" data-field-name="${esc(field.name)}">${options}</select>
      </div>
    `
  }

  const useTextarea = /allowed/i.test(field.name || '')
  const required = field.required ? ' required' : ''
  const inputType = field.type === 'password' ? 'password' : (field.type || 'text')
  if (useTextarea) {
    return `
      <div class="channels-field">
        <label for="${esc(id)}">${esc(label)}</label>
        <textarea id="${esc(id)}" data-field-name="${esc(field.name)}" placeholder="${esc(placeholder)}"${required}>${esc(value)}</textarea>
      </div>
    `
  }
  return `
    <div class="channels-field">
      <label for="${esc(id)}">${esc(label)}</label>
      <input id="${esc(id)}" type="${esc(inputType)}" data-field-name="${esc(field.name)}" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="${field.secret ? 'new-password' : 'off'}"${required}>
    </div>
  `
}

function _renderChannelMeta(channel) {
  if (!channel || channel.key !== 'weixin' || !channel.meta) return ''
  const items = []
  if (channel.meta.user_id) {
    items.push(`<div><strong>${esc(_channelsText('channels_meta_user_id', 'User ID'))}</strong> ${esc(channel.meta.user_id)}</div>`)
  }
  if (channel.meta.saved_at) {
    items.push(`<div><strong>${esc(_channelsText('channels_meta_saved_at', 'Saved at'))}</strong> ${esc(_formatChannelTime(channel.meta.saved_at))}</div>`)
  }
  return items.length ? `<div class="channels-meta">${items.join('')}</div>` : ''
}

function _weixinQrStatusText() {
  if (_weixinQrState.message) return _weixinQrState.message
  if (_weixinQrState.status === 'wait') return _channelsText('channels_qr_wait', 'Waiting for scan')
  if (_weixinQrState.status === 'scanned') return _channelsText('channels_qr_scanned', 'QR code scanned; confirm login in WeChat')
  if (_weixinQrState.status === 'expired') return _channelsText('channels_qr_expired', 'QR code expired; refreshed automatically')
  if (_weixinQrState.status === 'confirmed') return _channelsText('channels_qr_confirmed', 'Weixin account connected')
  if (_weixinQrState.status === 'failed') return _channelsText('channels_qr_failed', 'Weixin QR flow failed')
  return _channelsText('channels_qr_body', 'Start a QR session in this browser, then scan it with WeChat.')
}

function _renderWeixinBlock(channel) {
  const runtimeWarning = channel.runtime_ready === false
    ? `<div class="channels-card-warning">${esc(_channelsText('channels_weixin_runtime_missing', 'Weixin gateway runtime dependencies are missing in this container. Install the matching hermes-agent messaging extras first.'))}</div>`
    : ''
  const actionLabel = _weixinQrState.pollToken
    ? _channelsText('channels_restart_qr', 'Restart QR')
    : _channelsText('channels_start_qr', 'Start QR')
  return `
    <div class="channels-qr">
      <div class="channels-qr-title">${esc(_channelsText('channels_qr_title', 'QR connect'))}</div>
      <div class="channels-qr-body">${esc(_channelsText('channels_qr_body', 'Start a QR session in this browser, then scan it with WeChat. The QR image is rendered locally from the returned scan URL.'))}</div>
      ${runtimeWarning}
      <div class="channels-card-actions">
        <button class="cron-btn run" type="button" onclick="startWeixinQr()" ${channel.runtime_ready === false ? 'disabled' : ''}>${esc(actionLabel)}</button>
      </div>
      <div class="channels-qr-canvas" id="weixinQrCanvas">
        <div class="channels-qr-canvas-empty">${esc(_weixinQrState.qrcodeUrl ? _channelsText('loading', 'Loading...') : _channelsText('channels_qr_waiting_start', 'Start a QR session to render the code here.'))}</div>
      </div>
      <div class="channels-qr-status" id="weixinQrStatus">${esc(_weixinQrStatusText())}</div>
    </div>
  `
}

function _collectChannelPayload(key) {
  const form = $(`channelsForm-${key}`)
  const payload = {}
  if (!form) return payload
  form.querySelectorAll('[data-field-name]').forEach(field => {
    payload[field.dataset.fieldName] = field.value
  })
  return payload
}

function _replaceChannelState(channel) {
  if (!_channelsState) _channelsState = { channels: [] }
  const channels = Array.isArray(_channelsState.channels) ? _channelsState.channels : []
  const idx = channels.findIndex(item => item.key === channel.key)
  if (idx >= 0) channels[idx] = channel
  else channels.push(channel)
  _channelsState.channels = channels
}

async function saveChannel(key) {
  try {
    const channel = await api(`/api/channels/${encodeURIComponent(key)}/save`, {
      method: 'POST',
      body: JSON.stringify(_collectChannelPayload(key)),
    })
    _replaceChannelState(channel)
    if (key === 'weixin' && !channel.runtime_ready) {
      _closeWeixinQrStream()
    }
    _renderChannelsPanel(_channelsState)
    showToast(_channelsText('channels_saved', 'Channel settings saved'))
  } catch (err) {
    showToast((_channelsText('error_prefix', 'Error: ')) + (err.message || _channelsText('channels_unknown_error', 'Unknown error.')), 4000)
  }
}

async function testChannel(key) {
  try {
    const result = await api(`/api/channels/${encodeURIComponent(key)}/test`, {
      method: 'POST',
      body: JSON.stringify(_collectChannelPayload(key)),
    })
    showToast(result.message || _channelsText('channels_test_ok', 'Connection verified'))
  } catch (err) {
    showToast((_channelsText('error_prefix', 'Error: ')) + (err.message || _channelsText('channels_unknown_error', 'Unknown error.')), 4000)
  }
}

async function deleteChannel(key) {
  const confirmed = await showConfirmDialog({
    title: _channelsText('channels_delete_confirm_title', 'Delete channel config'),
    message: _channelsText('channels_delete_confirm_message', 'Stored credentials for this channel will be removed from the active profile.'),
    confirmLabel: _channelsText('delete_title', 'Delete'),
    danger: true,
    focusCancel: true,
  })
  if (!confirmed) return
  try {
    const result = await api(`/api/channels/${encodeURIComponent(key)}`, { method: 'DELETE' })
    if (key === 'weixin') {
      _closeWeixinQrStream()
      _resetWeixinQrState()
    }
    if (result && result.channel) _replaceChannelState(result.channel)
    _renderChannelsPanel(_channelsState)
    showToast(_channelsText('channels_deleted', 'Channel settings deleted'))
  } catch (err) {
    showToast((_channelsText('error_prefix', 'Error: ')) + (err.message || _channelsText('channels_unknown_error', 'Unknown error.')), 4000)
  }
}

async function startWeixinQr() {
  const profileName = _channelsProfileName()
  const channel = _channelsState && Array.isArray(_channelsState.channels)
    ? _channelsState.channels.find(item => item.key === 'weixin')
    : null
  if (channel && channel.runtime_ready === false) {
    showToast(_channelsText('channels_weixin_runtime_missing', 'Weixin gateway runtime dependencies are missing in this container. Install the matching hermes-agent messaging extras first.'), 4000)
    return
  }

  if (!_loadWeixinRiskAck(profileName)) {
    const confirmed = await showConfirmDialog({
      title: _channelsText('weixin_ilink_warning_title', 'Acknowledge Weixin iLink risk'),
      message: _channelsText('weixin_ilink_warning_body', 'The Weixin QR flow uses the community-supported iLink bridge, which is unofficial. WeChat risk controls may restrict or suspend the account after scanning. Do not use a production or high-value personal account unless you accept that risk.'),
      checkboxLabel: _channelsText('weixin_ilink_warning_acknowledge', 'I understand this is an unofficial integration and accept the WeChat account risk.'),
      requireCheckbox: true,
      confirmLabel: _channelsText('channels_start_qr', 'Start QR'),
      danger: true,
      focusCheckbox: true,
    })
    if (!confirmed) return
    _weixinQrState.disclosureAccepted = true
    _storeWeixinRiskAck(profileName, true)
  }

  try {
    _closeWeixinQrStream()
    const payload = await api('/api/channels/weixin/qr/start', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    _weixinQrState.active = true
    _weixinQrState.pollToken = String(payload.poll_token || '')
    _weixinQrState.qrcodeUrl = String(payload.qrcode_url || '')
    _weixinQrState.status = 'wait'
    _weixinQrState.message = ''
    _weixinQrState.refreshes = 0
    _renderWeixinQrCanvas()
    _openWeixinQrStream()
  } catch (err) {
    _weixinQrState.status = 'failed'
    _weixinQrState.message = err.message || _channelsText('channels_unknown_error', 'Unknown error.')
    _renderWeixinQrCanvas()
    showToast((_channelsText('error_prefix', 'Error: ')) + _weixinQrState.message, 4000)
  }
}

async function _runGatewayAction(action) {
  if (_gatewayActionState.busy) return
  if (action === 'restart') {
    const confirmed = await showConfirmDialog({
      title: _channelsText('channels_gateway_restart_confirm_title', 'Restart gateway'),
      message: _channelsText('channels_gateway_restart_confirm_message', 'Restart the managed gateway service for the current profile? Active channel traffic may reconnect.'),
      confirmLabel: _channelsText('channels_gateway_restart', 'Restart'),
      danger: true,
      focusCancel: true,
    })
    if (!confirmed) return
  }

  _gatewayActionState = { busy: true, action }
  _renderGatewayStatus((_channelsState && _channelsState.gateway) || {})

  try {
    const result = await api(`/api/gateway/${encodeURIComponent(action)}`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    if (_channelsState && result && result.gateway) _channelsState.gateway = result.gateway
    showToast((result && result.summary) || _channelsText('channels_saved', 'Saved'))
  } catch (err) {
    showToast((_channelsText('error_prefix', 'Error: ')) + (err.message || _channelsText('channels_unknown_error', 'Unknown error.')), 5000)
  } finally {
    _gatewayActionState = { busy: false, action: '' }
    await loadChannelsPanel(true)
  }
}

async function startGateway() {
  await _runGatewayAction('start')
}

async function restartGateway() {
  await _runGatewayAction('restart')
}

function _renderWeixinQrCanvas() {
  const canvas = $('weixinQrCanvas')
  const status = $('weixinQrStatus')
  if (status) status.textContent = _weixinQrStatusText()
  if (!canvas) return

  if (!_weixinQrState.qrcodeUrl) {
    canvas.innerHTML = `<div class="channels-qr-canvas-empty">${esc(_channelsText('channels_qr_waiting_start', 'Start a QR session to render the code here.'))}</div>`
    return
  }

  if (!window.QRCode) {
    canvas.innerHTML = `<div class="channels-qr-canvas-empty">${esc(_weixinQrState.qrcodeUrl)}</div>`
    return
  }

  canvas.innerHTML = ''
  const opts = {
    text: _weixinQrState.qrcodeUrl,
    width: 188,
    height: 188,
    colorDark: '#0e1726',
    colorLight: '#ffffff',
  }
  if (window.QRCode.CorrectLevel && window.QRCode.CorrectLevel.M) {
    opts.correctLevel = window.QRCode.CorrectLevel.M
  }
  new window.QRCode(canvas, opts)
}

function _closeWeixinQrStream() {
  if (_weixinQrSource) {
    _weixinQrSource.close()
    _weixinQrSource = null
  }
}

function _openWeixinQrStream() {
  _closeWeixinQrStream()
  if (!_weixinQrState.pollToken) return
  const url = new URL(`api/channels/weixin/qr/stream?poll_token=${encodeURIComponent(_weixinQrState.pollToken)}`, location.href)
  const source = new EventSource(url.href)
  _weixinQrSource = source

  source.addEventListener('wait', event => {
    const payload = _channelsParseEvent(event)
    _weixinQrState.active = true
    _weixinQrState.status = 'wait'
    _weixinQrState.message = ''
    if (payload.qrcode_url) _weixinQrState.qrcodeUrl = String(payload.qrcode_url)
    _renderWeixinQrCanvas()
  })

  source.addEventListener('scanned', () => {
    _weixinQrState.active = true
    _weixinQrState.status = 'scanned'
    _weixinQrState.message = ''
    _renderWeixinQrCanvas()
  })

  source.addEventListener('expired', event => {
    const payload = _channelsParseEvent(event)
    _weixinQrState.active = true
    _weixinQrState.status = 'expired'
    _weixinQrState.message = ''
    _weixinQrState.refreshes = Number(payload.refreshes || 0)
    if (payload.qrcode_url) _weixinQrState.qrcodeUrl = String(payload.qrcode_url)
    _renderWeixinQrCanvas()
  })

  source.addEventListener('confirmed', async event => {
    const payload = _channelsParseEvent(event)
    _weixinQrState.active = false
    _weixinQrState.status = 'confirmed'
    _weixinQrState.message = payload.account_id
      ? `${_channelsText('channels_qr_confirmed', 'Weixin account connected')}: ${payload.account_id}`
      : _channelsText('channels_qr_confirmed', 'Weixin account connected')
    _closeWeixinQrStream()
    _renderWeixinQrCanvas()
    showToast(_channelsText('channels_qr_confirmed', 'Weixin account connected'))
    await loadChannelsPanel(true)
  })

  source.addEventListener('failed', event => {
    const payload = _channelsParseEvent(event)
    _weixinQrState.active = false
    _weixinQrState.status = 'failed'
    _weixinQrState.message = String(payload.message || _channelsText('channels_qr_failed', 'Weixin QR flow failed'))
    _closeWeixinQrStream()
    _renderWeixinQrCanvas()
    showToast(_weixinQrState.message, 4000)
  })

  source.onerror = () => {
    if (_weixinQrSource !== source) return
    _weixinQrState.active = false
    _weixinQrState.status = 'failed'
    _weixinQrState.message = _channelsText('channels_unknown_error', 'Unknown error.')
    _closeWeixinQrStream()
    _renderWeixinQrCanvas()
  }
}

async function copyChannelsHome() {
  const home = _channelsState && _channelsState.gateway ? _channelsState.gateway.hermes_home : ''
  if (!home) return
  try {
    await navigator.clipboard.writeText(home)
    showToast(_channelsText('channels_copy_path_done', 'Copied path'))
  } catch (_) {
    showToast(_channelsText('copy_failed', 'Copy failed'), 3000)
  }
}
