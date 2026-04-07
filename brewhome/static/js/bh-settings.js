// ══════════════════════════════════════════════════════════════════════════════
// FUSEAU HORAIRE
// ══════════════════════════════════════════════════════════════════════════════
function getTzOffset() {
  return parseFloat((appSettings.tz_offset !== undefined ? appSettings.tz_offset : 0)) || 0;
}
function fmtReadingDate(dateStr) {
  if (!dateStr) return '—';
  // SQLite renvoie '2024-01-15 14:30:00' — remplacer l'espace par T pour un parsing ISO fiable
  const d = new Date(dateStr.replace(' ', 'T'));
  if (isNaN(d.getTime())) return dateStr;
  d.setHours(d.getHours() + getTzOffset());
  return d.toLocaleString(_lang || 'fr', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'});
}
function saveTzOffset() {
  const v = parseFloat(document.getElementById('tz-offset')?.value);
  appSettings.tz_offset = isNaN(v) ? 0 : v;
  saveSettings();
  renderSpindles();
  renderBrassins();
  toast(t('spin.tz_saved'), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// DONNÉES DENSIMÈTRES — STATS ET PURGE
// ══════════════════════════════════════════════════════════════════════════════
async function loadSpindleStats() {
  const _fmt = (stats, label) => {
    const lang   = _lang || 'fr';
    const n      = (stats.total || 0).toLocaleString(lang);
    const oldest = stats.oldest ? new Date(stats.oldest).toLocaleDateString(lang) : '—';
    const unit   = stats.total !== 1 ? t('spin.readings') : t('spin.reading');
    return `${n} ${unit} ${label}· ${t('spin.stats_since')} ${oldest}`;
  };
  try {
    const [spinStats, tempStats] = await Promise.all([
      api('GET', '/api/spindle/readings/stats'),
      api('GET', '/api/temperature/readings/stats'),
    ]);
    const elSpin = document.getElementById('spin-db-stats');
    const elTemp = document.getElementById('temp-db-stats');
    if (elSpin) elSpin.textContent = _fmt(spinStats, t('spin.metric_gravity').toLowerCase() + ' ');
    if (elTemp) elTemp.textContent = _fmt(tempStats, t('spin.metric_temp').toLowerCase() + ' ');
  } catch(e) {}
}

async function purgeReadings() {
  const days = parseInt(document.getElementById('purge-days')?.value || '30');
  if (!await confirmModal(t('spin.purge_confirm').replace('${days}', days), { danger: true })) return;
  try {
    const r = await api('DELETE', `/api/spindle/readings/purge?days=${days}`);
    toast(t('spin.purge_success').replace('${deleted}', r.deleted).replace('${remaining}', r.remaining), 'success');
    S.spindles = await api('GET', '/api/spindles');
    renderSpindles();
    loadSpindleStats();
  } catch(e) { toast(t('spin.err_purge'), 'error'); }
}

async function purgeTempReadings() {
  const days = parseInt(document.getElementById('purge-temp-days')?.value || '30');
  if (!await confirmModal(t('spin.purge_confirm').replace('${days}', days), { danger: true })) return;
  try {
    const r = await api('DELETE', `/api/temperature/readings/purge?days=${days}`);
    toast(t('spin.purge_success').replace('${deleted}', r.deleted).replace('${remaining}', r.remaining), 'success');
    S.tempSensors = await api('GET', '/api/temperature');
    renderTempSensors();
    loadSpindleStats();
  } catch(e) { toast(t('spin.err_purge'), 'error'); }
}

async function purgeUnassignedTempReadings() {
  if (!await confirmModal(t('spin.purge_unassigned_confirm'), { danger: true })) return;
  try {
    const r = await api('DELETE', '/api/temperature/readings/purge?unassigned=true');
    toast(t('spin.purge_success').replace('${deleted}', r.deleted).replace('${remaining}', r.remaining), 'success');
    loadSpindleStats();
  } catch(e) { toast(t('spin.err_purge'), 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════════
// SONDES DE TEMPÉRATURE
// ══════════════════════════════════════════════════════════════════════════════

let _editTempId   = null;
let _tempChart    = null;
let _tempSensorId = null;
let _tempChartSeq = 0;  // anti-race : ignore les réponses obsolètes

function renderTempSensors() {
  const grid  = document.getElementById('temp-sensor-grid');
  const empty = document.getElementById('temp-sensor-empty');
  if (!grid) return;

  if (!S.tempSensors.length) {
    grid.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = S.tempSensors.map(s => {
    const lastAt      = fmtReadingDate(s.last_reading_at);
    const age         = spindleAge(s.last_reading_at);
    const tempVal     = s.last_temperature;
    const humVal      = s.last_humidity;
    const targetVal   = s.last_target_temp;
    const hvacMode    = s.last_hvac_mode;
    const isThermostat = s.sensor_type === 'thermostat';
    const tempStr     = tempVal   != null ? tempVal.toFixed(1)   + ' °C' : '—';
    const humStr      = humVal    != null ? humVal.toFixed(1)    + ' %'  : null;
    const targetStr   = targetVal != null ? targetVal.toFixed(1) + ' °C' : null;

    // Badge type d'entité
    const typeBadge = isThermostat
      ? `<span style="font-size:.68rem;padding:1px 7px;border-radius:8px;background:#8b5cf620;color:#8b5cf6;font-weight:700;margin-left:6px;vertical-align:middle"><i class="fas fa-sliders"></i> Thermostat</span>`
      : '';

    // Badge mode HVAC
    const hvacInfo = (() => {
      if (!isThermostat || !hvacMode) return '';
      const modes = { heat: { icon: 'fa-fire', color: '#ef4444', label: 'Chauffe' }, cool: { icon: 'fa-snowflake', color: '#3b82f6', label: 'Refroid.' }, off: { icon: 'fa-power-off', color: '#6b7280', label: 'Arrêt' } };
      const m = modes[hvacMode] || { icon: 'fa-circle', color: '#6b7280', label: hvacMode };
      return `<span style="font-size:.72rem;padding:2px 7px;border-radius:8px;background:${m.color}20;color:${m.color};font-weight:700"><i class="fas ${m.icon}"></i> ${m.label}</span>`;
    })();

    // Alerte de seuil
    let alertBadge = '';
    let cardBorder = age.color;
    if (tempVal != null) {
      if (s.temp_min != null && tempVal < s.temp_min) {
        alertBadge = `<span style="font-size:.72rem;padding:2px 8px;border-radius:10px;background:#3b82f620;color:#3b82f6;font-weight:700;margin-left:6px"><i class="fas fa-arrow-down"></i> Sous le seuil</span>`;
        cardBorder = '#3b82f6';
      } else if (s.temp_max != null && tempVal > s.temp_max) {
        alertBadge = `<span style="font-size:.72rem;padding:2px 8px;border-radius:10px;background:#ef444420;color:#ef4444;font-weight:700;margin-left:6px"><i class="fas fa-arrow-up"></i> Hors seuil</span>`;
        cardBorder = '#ef4444';
      }
    }

    const thresholdInfo = (s.temp_min != null || s.temp_max != null)
      ? `<span style="font-size:.75rem;color:var(--muted)">${s.temp_min != null ? s.temp_min + '°' : '—'} → ${s.temp_max != null ? s.temp_max + '°' : '—'}</span>`
      : '';

    return `
      <div class="spindle-card" data-id="${s.id}" style="border-color:${cardBorder}44">
        <div class="spindle-card-head">
          <div style="display:flex;align-items:center;gap:4px;min-width:0">
            <div class="spindle-name">
              <i class="fas fa-thermometer-half" style="color:#ef4444;margin-right:7px"></i>${esc(s.name)}${typeBadge}${alertBadge}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="spindle-age-badge${age.fresh ? ' spindle-age-pulse' : ''}" style="color:${age.color};background:${age.color}1a;border-color:${age.color}55" title="${t('spin.last_received')} : ${lastAt}">
              <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${age.color};flex-shrink:0"></span>
              ${age.label}
            </span>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="showTempSensorToken(${s.id})" title="${t('spin.ha_config')}"><i class="fas fa-key"></i></button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openTempChart(${s.id})" title="${t('spin.chart_temp_label')}"><i class="fas fa-chart-line"></i></button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openTempSensorEditModal(${s.id})" title="${t('common.edit')}"><i class="fas fa-pen"></i></button>
            <button class="btn btn-danger btn-sm btn-icon" onclick="deleteTempSensor(${s.id})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
          </div>
        </div>
        <div class="spindle-metrics">
          <div class="spindle-metric">
            <div class="spindle-metric-val" style="font-size:1.6rem;color:${tempVal != null && ((s.temp_min != null && tempVal < s.temp_min) || (s.temp_max != null && tempVal > s.temp_max)) ? '#ef4444' : 'inherit'}" title="${tempVal != null ? t('spin.last_received') + ' : ' + lastAt : ''}">${tempStr}</div>
            <div class="spindle-metric-lbl">Température${thresholdInfo ? '&nbsp;' + thresholdInfo : ''}</div>
          </div>
          ${isThermostat && targetStr ? `<div class="spindle-metric">
            <div class="spindle-metric-val" style="font-size:1.3rem" title="${t('spin.last_received')} : ${lastAt}">${targetStr}</div>
            <div class="spindle-metric-lbl">Consigne</div>
          </div>` : ''}
          ${!isThermostat && humStr ? `<div class="spindle-metric">
            <div class="spindle-metric-val" title="${t('spin.last_received')} : ${lastAt}">${humStr}</div>
            <div class="spindle-metric-lbl">Humidité</div>
          </div>` : ''}
          ${isThermostat && hvacInfo ? `<div class="spindle-metric">
            <div class="spindle-metric-val" style="font-size:.85rem" title="${t('spin.last_received')} : ${lastAt}">${hvacInfo}</div>
            <div class="spindle-metric-lbl">Mode</div>
          </div>` : ''}
        </div>
        ${s.notes ? `<div style="font-size:.78rem;color:var(--muted);margin-top:6px"><i class="fas fa-note-sticky"></i> ${esc(s.notes)}</div>` : ''}
        <div class="spindle-brew-link">
          <i class="fas fa-link" style="color:#ef4444;flex-shrink:0"></i>
          <select style="flex:1;border:none;background:transparent;color:var(--text);font-family:inherit;font-size:.85rem;cursor:pointer"
                  onchange="linkTempSensorBrew(${s.id}, this.value)">
            <option value="">${t('spin.not_linked_brew')}</option>
            ${(() => {
              const otherIds = new Set(S.tempSensors.filter(ts => ts.brew_id && ts.id !== s.id).map(ts => ts.brew_id));
              const available = S.brews.filter(b => !b.archived && !otherIds.has(b.id));
              const active    = available.filter(b => b.status !== 'completed');
              const done      = available.filter(b => b.status === 'completed');
              return [
                active.length ? `<optgroup label="${t('spin.brew_in_progress')}">` + active.map(b => `<option value="${b.id}" ${s.brew_id == b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('') + `</optgroup>` : '',
                done.length   ? `<optgroup label="${t('spin.brew_completed')}">` + done.map(b => `<option value="${b.id}" ${s.brew_id == b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('') + `</optgroup>` : '',
              ].join('');
            })()}
          </select>
        </div>
        <div style="font-size:.78rem;color:var(--muted);margin-top:6px">
          <i class="fas fa-clock"></i> ${t('spin.last_seen')} : ${lastAt}
          &nbsp;·&nbsp;<i class="fas fa-database"></i> ${s.reading_count || 0} ${(s.reading_count || 0) !== 1 ? t('spin.readings') : t('spin.reading')}
        </div>
      </div>`;
  }).join('');
}

function _tempUpdateHaFields() {
  const type = document.getElementById('temp-f-type').value;
  const isThermostat = type === 'thermostat';
  document.getElementById('temp-f-entity-label').textContent =
    (isThermostat ? t('spin.temp_entity_thermostat') : t('spin.temp_entity')) + ' ' + t('common.optional');
  document.getElementById('temp-f-entity').placeholder =
    isThermostat ? 'Ex : climate.itc_308_wifi_thermostat' : 'Ex : sensor.inkbird_itc308_temperature_probe';
  document.getElementById('temp-f-entity-hum-wrap').style.display = isThermostat ? 'none' : '';
}

function openTempSensorModal() {
  _editTempId = null;
  document.getElementById('temp-modal-title').textContent = t('spin.temp_add');
  document.getElementById('temp-f-name').value       = '';
  document.getElementById('temp-f-type').value       = 'sensor';
  document.getElementById('temp-f-entity').value     = '';
  document.getElementById('temp-f-entity-hum').value = '';
  document.getElementById('temp-f-notes').value      = '';
  document.getElementById('temp-f-min').value        = '';
  document.getElementById('temp-f-max').value        = '';
  document.getElementById('temp-token-section').style.display = 'none';
  document.getElementById('temp-save-btn').style.display = '';
  document.getElementById('temp-save-btn').innerHTML = `<i class="fas fa-plus"></i> ${t('spin.create')}`;
  _tempUpdateHaFields();
  openModal('temp-sensor-modal');
}

function openTempSensorEditModal(id) {
  const s = S.tempSensors.find(x => x.id === id);
  if (!s) return;
  _editTempId = id;
  document.getElementById('temp-modal-title').textContent = `${t('common.edit')} — ${s.name}`;
  document.getElementById('temp-f-name').value       = s.name;
  document.getElementById('temp-f-type').value       = s.sensor_type || 'sensor';
  document.getElementById('temp-f-entity').value     = s.ha_entity || '';
  document.getElementById('temp-f-entity-hum').value = s.ha_entity_hum || '';
  document.getElementById('temp-f-notes').value      = s.notes || '';
  document.getElementById('temp-f-min').value        = s.temp_min ?? '';
  document.getElementById('temp-f-max').value        = s.temp_max ?? '';
  document.getElementById('temp-token-section').style.display = 'none';
  document.getElementById('temp-save-btn').style.display = '';
  document.getElementById('temp-save-btn').innerHTML = `<i class="fas fa-floppy-disk"></i> ${t('common.save')}`;
  _tempUpdateHaFields();
  openModal('temp-sensor-modal');
}

async function saveTempSensor() {
  const name = document.getElementById('temp-f-name').value.trim();
  if (!name) { toast(t('spin.name_required'), 'error'); return; }
  const sensor_type   = document.getElementById('temp-f-type').value;
  const ha_entity     = document.getElementById('temp-f-entity').value.trim() || null;
  const ha_entity_hum = document.getElementById('temp-f-entity-hum').value.trim() || null;
  const notes    = document.getElementById('temp-f-notes').value.trim() || null;
  const temp_min = document.getElementById('temp-f-min').value !== '' ? parseFloat(document.getElementById('temp-f-min').value) : null;
  const temp_max = document.getElementById('temp-f-max').value !== '' ? parseFloat(document.getElementById('temp-f-max').value) : null;
  const payload  = { name, sensor_type, ha_entity, ha_entity_hum, notes, temp_min, temp_max };

  if (_editTempId !== null) {
    try {
      const updated = await api('PATCH', `/api/temperature/${_editTempId}`, payload);
      const idx = S.tempSensors.findIndex(x => x.id === _editTempId);
      if (idx !== -1) S.tempSensors[idx] = updated;
      renderTempSensors();
      closeModal('temp-sensor-modal');
      toast(t('spin.temp_updated'), 'success');
    } catch(e) { toast(t('spin.err_update'), 'error'); }
    return;
  }

  try {
    const s = await api('POST', '/api/temperature', payload);
    S.tempSensors.unshift(s);
    renderTempSensors();
    document.getElementById('temp-token-display').textContent = s.token;
    document.getElementById('temp-token-section').style.display = '';
    document.getElementById('temp-save-btn').style.display = 'none';
    toast(t('spin.temp_created'), 'success');
  } catch(e) { toast(t('spin.err_create'), 'error'); }
}

function copyTempToken() {
  const tok = document.getElementById('temp-token-display').textContent;
  navigator.clipboard.writeText(tok).then(() => toast(t('spin.token_copied'), 'success'));
}

async function deleteTempSensor(id) {
  if (!await confirmModal(t('spin.confirm_delete_temp'), { danger: true })) return;
  try {
    await api('DELETE', `/api/temperature/${id}`);
    S.tempSensors = S.tempSensors.filter(x => x.id !== id);
    renderTempSensors();
    toast(t('spin.temp_deleted'), 'success');
  } catch(e) { toast(t('spin.err_delete'), 'error'); }
}

async function linkTempSensorBrew(sensorId, brewId) {
  try {
    const updated = await api('PATCH', `/api/temperature/${sensorId}`, {
      brew_id: brewId ? parseInt(brewId) : null,
    });
    const idx = S.tempSensors.findIndex(s => s.id === sensorId);
    if (idx !== -1) S.tempSensors[idx] = updated;
    renderTempSensors();
    renderBrassins();
    toast(brewId ? t('spin.linked') : t('spin.unlinked'), 'success');
  } catch(e) { toast(t('spin.err_link'), 'error'); }
}

function showTempSensorToken(id) {
  const s = S.tempSensors.find(x => x.id === id);
  if (!s) return;
  const url        = `${window.location.origin}/api/temperature/data?token=${s.token}`;
  const sensorSlug = s.name.toLowerCase().replace(/[^a-z0-9]/g, '_');

  document.getElementById('tha-sensor-name').textContent = s.name;
  document.getElementById('tha-token').textContent = s.token;
  document.getElementById('tha-url').textContent   = url;

  let yamlConf, yamlAuto;

  if (s.sensor_type === 'thermostat') {
    const entity  = s.ha_entity || 'climate.ENTITE_THERMOSTAT';
    const warning = s.ha_entity ? '' : '\n# ⚠ Remplacer climate.ENTITE_THERMOSTAT par le nom de votre entité HA';
    yamlConf = `rest_command:
  brewhome_temp_${sensorSlug}:
    url: "${url}"
    method: POST
    content_type: "application/json"
    payload: >-
      {"temperature":{{ state_attr('${entity}','current_temperature')|float|round(1) }},"target_temp":{{ state_attr('${entity}','temperature')|float|round(1) }},"hvac_mode":"{{ states('${entity}') }}"}${warning}`;
  } else {
    const entityTemp = s.ha_entity     || 'sensor.ENTITE_TEMPERATURE';
    const entityHum  = s.ha_entity_hum || 'sensor.ENTITE_HUMIDITE';
    const parts = [];
    if (!s.ha_entity)     parts.push('sensor.ENTITE_TEMPERATURE');
    if (!s.ha_entity_hum) parts.push('sensor.ENTITE_HUMIDITE');
    const warning = parts.length ? `\n# ⚠ Remplacer ${parts.join(' et ')} par vos entités HA réelles` : '';
    yamlConf = `rest_command:
  brewhome_temp_${sensorSlug}:
    url: "${url}"
    method: POST
    content_type: "application/json"
    payload: >-
      {"temperature":{{ states('${entityTemp}')|float|round(1) }},"humidity":{{ states('${entityHum}')|float|round(1)|default(none) }}}${warning}`;
  }

  yamlAuto = `- alias: "BrewHome — ${s.name}"
  trigger:
    - platform: time_pattern
      minutes: "/5"
  action:
    - action: rest_command.brewhome_temp_${sensorSlug}`;

  document.getElementById('tha-yaml-conf').textContent = yamlConf;
  document.getElementById('tha-yaml-auto').textContent = yamlAuto;
  openModal('temp-ha-modal');
}

function copyThaToken() {
  navigator.clipboard.writeText(document.getElementById('tha-token').textContent)
    .then(() => toast(t('spin.token_copied'), 'success'));
}

function copyThaUrl() {
  navigator.clipboard.writeText(document.getElementById('tha-url').textContent)
    .then(() => toast(t('spin.url_copied'), 'success'));
}

function copyThaYamlConf() {
  navigator.clipboard.writeText(document.getElementById('tha-yaml-conf').textContent)
    .then(() => toast('configuration.yaml ' + t('common.copied'), 'success'));
}

function copyThaYamlAuto() {
  navigator.clipboard.writeText(document.getElementById('tha-yaml-auto').textContent)
    .then(() => toast('automations.yaml ' + t('common.copied'), 'success'));
}

async function openTempChart(sensorId) {
  const s = S.tempSensors.find(x => x.id === sensorId);
  _tempSensorId = sensorId;
  document.getElementById('temp-chart-title').textContent =
    t('spin.temp_chart_title').replace('${name}', s ? esc(s.name) : '');
  document.querySelectorAll('.tc-range').forEach((b, i) => {
    b.classList.toggle('btn-primary', i === 0);
    b.classList.toggle('btn-ghost',   i !== 0);
  });
  document.getElementById('tc-custom-range').style.display = 'none';
  openModal('temp-chart-modal');
  await _loadTempChart({ hours: 24 });
}

async function _loadTempChart({ hours, from, to } = {}) {
  const seq = ++_tempChartSeq;
  if (_tempChart) { _tempChart.destroy(); _tempChart = null; }
  const stale = Chart.getChart('temp-chart-canvas');
  if (stale) stale.destroy();
  document.getElementById('temp-chart-table').innerHTML =
    `<p style="text-align:center;color:var(--muted);padding:20px 0"><i class="fas fa-spinner fa-spin"></i> ${t('common.loading')}</p>`;

  let url = `/api/temperature/${_tempSensorId}/readings`;
  const params = [];
  if (hours)  params.push(`hours=${hours}`);
  if (from)   params.push(`from=${encodeURIComponent(from)}`);
  if (to)     params.push(`to=${encodeURIComponent(to)}`);
  params.push('limit=2000');
  if (params.length) url += '?' + params.join('&');

  try {
    const readings = await api('GET', url);
    if (seq !== _tempChartSeq) return;  // requête obsolète, une plus récente a pris le relais
    const s = S.tempSensors.find(x => x.id === _tempSensorId);
    const tz = getTzOffset ? getTzOffset() : 0;
    const labels = readings.map(r => {
      const d = new Date(r.recorded_at.replace(' ', 'T'));
      if (tz) d.setTime(d.getTime() + tz * 3600000);
      return d.toLocaleString(_lang || 'fr', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
    });
    const temps = readings.map(r => r.temperature);
    const hums  = readings.map(r => r.humidity);
    const hasHum = hums.some(h => h != null);

    const datasets = [{
      label: `${t('spin.metric_temp')} (°C)`,
      data: temps,
      borderColor: '#ef4444',
      backgroundColor: 'rgba(239,68,68,.08)',
      borderWidth: 2,
      pointRadius: readings.length > 200 ? 0 : 3,
      tension: 0.3,
      fill: true,
      yAxisID: 'yTemp',
    }];
    if (hasHum) {
      datasets.push({
        label: 'Humidité (%)',
        data: hums,
        borderColor: '#3b82f6',
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        yAxisID: 'yHum',
      });
    }

    // Lignes de seuil
    const annotations = {};
    if (s?.temp_min != null) {
      annotations.minLine = { type:'line', yMin:s.temp_min, yMax:s.temp_min, borderColor:'#3b82f6', borderWidth:1.5, borderDash:[4,4], yScaleID:'yTemp',
        label:{ content:`Min ${s.temp_min}°C`, enabled:true, position:'end', backgroundColor:'#3b82f6', font:{size:10} } };
    }
    if (s?.temp_max != null) {
      annotations.maxLine = { type:'line', yMin:s.temp_max, yMax:s.temp_max, borderColor:'#ef4444', borderWidth:1.5, borderDash:[4,4], yScaleID:'yTemp',
        label:{ content:`Max ${s.temp_max}°C`, enabled:true, position:'end', backgroundColor:'#ef4444', font:{size:10} } };
    }

    const scales = {
      x:     { ticks:{ maxTicksLimit:8, font:{size:10} }, grid:{ color:'rgba(128,128,128,.1)' } },
      yTemp: { position:'left',  ticks:{ font:{size:10}, callback:v => v+'°C' }, grid:{ color:'rgba(128,128,128,.1)' }, title:{ display:true, text:'°C', font:{size:10} } },
    };
    if (hasHum) {
      scales.yHum = { position:'right', ticks:{ font:{size:10}, callback:v => v+'%' }, grid:{ drawOnChartArea:false }, title:{ display:true, text:'Humidité %', font:{size:10} } };
    }

    _tempChart = new Chart(document.getElementById('temp-chart-canvas'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode:'index', intersect:false },
        plugins: { legend:{ labels:{ font:{size:11} } }, annotation:{ annotations } },
        scales,
      },
    });

    // Tableau des 10 dernières mesures
    const last10 = [...readings].reverse().slice(0, 10);
    if (!last10.length) {
      document.getElementById('temp-chart-table').innerHTML = `<p style="text-align:center;color:var(--muted)">${t('brew.no_readings_temp')}</p>`;
    } else {
      document.getElementById('temp-chart-table').innerHTML = `
        <table style="width:100%;font-size:.8rem;border-collapse:collapse">
          <thead><tr style="color:var(--muted)">
            <th style="text-align:left;padding:4px 8px">Date / heure</th>
            <th style="text-align:right;padding:4px 8px">Température</th>
            ${hasHum ? '<th style="text-align:right;padding:4px 8px">Humidité</th>' : ''}
          </tr></thead>
          <tbody>${last10.map(r => {
            const d = new Date(r.recorded_at.replace(' ', 'T'));
            if (tz) d.setTime(d.getTime() + tz * 3600000);
            const dt = d.toLocaleString(_lang || 'fr', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
            const alert = s && r.temperature != null && ((s.temp_min != null && r.temperature < s.temp_min) || (s.temp_max != null && r.temperature > s.temp_max));
            return `<tr style="border-top:1px solid var(--border)">
              <td style="padding:4px 8px;color:var(--muted)">${dt}</td>
              <td style="padding:4px 8px;text-align:right;font-weight:600;color:${alert ? '#ef4444' : 'inherit'}">${r.temperature != null ? r.temperature.toFixed(1) + ' °C' : '—'}</td>
              ${hasHum ? `<td style="padding:4px 8px;text-align:right">${r.humidity != null ? r.humidity.toFixed(1) + ' %' : '—'}</td>` : ''}
            </tr>`;
          }).join('')}</tbody>
        </table>`;
    }
  } catch(e) {
    if (seq === _tempChartSeq)
      document.getElementById('temp-chart-table').innerHTML = `<p style="color:var(--danger);text-align:center">${esc(e.message)}</p>`;
  }
}

function setTempRange(btn, range) {
  document.querySelectorAll('.tc-range').forEach(b => {
    b.classList.remove('btn-primary'); b.classList.add('btn-ghost');
  });
  btn.classList.remove('btn-ghost'); btn.classList.add('btn-primary');
  const customEl = document.getElementById('tc-custom-range');
  if (range === 'custom') { customEl.style.display = 'flex'; return; }
  customEl.style.display = 'none';
  _loadTempChart({ hours: range > 0 ? range : null });
}

function applyCustomTempRange() {
  const fromVal = document.getElementById('tc-from').value;
  const toVal   = document.getElementById('tc-to').value;
  if (!fromVal) { toast(t('spin.select_date_start'), 'error'); return; }
  const tz = getTzOffset ? getTzOffset() : 0;
  const toServerTs = str => {
    if (!str) return null;
    const d = new Date(str + ':00Z');
    d.setTime(d.getTime() - tz * 3600000);
    return d.toISOString().slice(0, 19).replace('T', ' ');
  };
  _loadTempChart({ from: toServerTs(fromVal), to: toServerTs(toVal) });
}

// ══════════════════════════════════════════════════════════════════════════════
// IMPORT / EXPORT
// ══════════════════════════════════════════════════════════════════════════════
function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

async function importHopsDb() {
  const btn = document.getElementById('btn-import-hopsteiner');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Import…'; }
  try {
    const res = await api('POST', '/api/catalog/import-hopsteiner');
    toast(t('settings.import.imported_hopsteiner').replace('${imported}', res.imported).replace('${updated}', res.updated), 'success');
    const cat = await api('GET', '/api/catalog');
    S.catalog = cat;
    renderSettingsCatalog(settingsCat);
  } catch(e) { toast(t('settings.import.err_import_hopsteiner') + ' ' + e.message, 'error'); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fas fa-cloud-arrow-down"></i> ${t('settings.import.btn_import_hopsteiner')}`; } }
}

async function exportCatalog() {
  const data = await api('GET', '/api/export/catalog');
  downloadJson(data, `catalogue_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_cat'), 'success');
}

async function importCatalog(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const res = await api('POST', '/api/import/catalog', items);
    toast(t('settings.import.imported_cat').replace('${n}', res.imported), 'success');
    const cat = await api('GET', '/api/catalog');
    S.catalog = cat;
    renderSettingsCatalog(settingsCat);
  } catch(e) { toast(t('settings.import.err_import_cat') + ' ' + e.message, 'error'); }
  input.value = '';
}

async function exportInventory() {
  const data = await api('GET', '/api/export/inventory');
  downloadJson(data, `inventaire_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_inv'), 'success');
}

async function exportRecipes() {
  const data = await api('GET', '/api/export/recipes');
  downloadJson(data, `recettes_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_rec'), 'success');
}

function triggerImport(inputId) {
  document.getElementById(inputId).click();
}

async function importInventory(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/inventory', items);
    toast(t('settings.import.imported_inv').replace('${n}', r.imported), 'success');
    S.inventory = await api('GET', '/api/inventory');
    renderInventaire();
  } catch(e) { toast(t('settings.import.err_import_inv'), 'error'); }
  input.value = '';
}

async function importRecipes(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/recipes', items);
    toast(t('settings.import.imported_rec').replace('${n}', r.imported), 'success');
    S.recipes = await api('GET', '/api/recipes');
    renderRecipeList();
  } catch(e) { toast(t('settings.import.err_import_rec'), 'error'); }
  input.value = '';
}

function exportBeerXML() {
  const a = document.createElement('a');
  a.href = '/api/export/beerxml';
  a.download = `recettes_${new Date().toISOString().slice(0,10)}.xml`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  toast(t('settings.import.exported_beerxml'), 'success');
}

async function importBeerXML(input) {
  const file = input.files[0];
  if (!file) return;
  const xml = await file.text();
  try {
    const r = await fetch('/api/import/beerxml', {
      method: 'POST',
      headers: {'Content-Type': 'application/xml'},
      body: xml
    });
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();
    toast(t('settings.import.imported_beerxml').replace('${n}', data.imported), 'success');
    S.recipes = await api('GET', '/api/recipes');
    renderRecipeList();
  } catch(e) { toast(t('settings.import.err_import_beerxml'), 'error'); }
  input.value = '';
}

async function importBrewfather(input) {
  const file = input.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    const r = await api('POST', '/api/import/brewfather', data);
    toast(t('settings.import.imported_brewfather').replace('${n}', r.imported), 'success');
    S.recipes = await api('GET', '/api/recipes');
    renderRecipeList();
  } catch(e) { toast(t('settings.import.err_import_brewfather'), 'error'); }
  input.value = '';
}

async function exportBeers() {
  const data = await api('GET', '/api/export/beers');
  downloadJson(data, `cave_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_cave'), 'success');
}

async function importBeers(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/beers', items);
    toast(t('settings.import.imported_cave').replace('${n}', r.imported), 'success');
    S.beers = await api('GET', '/api/beers');
    renderCave();
  } catch(e) { toast(t('settings.import.err_import_cave'), 'error'); }
  input.value = '';
}

async function exportBrews() {
  const data = await api('GET', '/api/export/brews');
  downloadJson(data, `brassins_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_brews'), 'success');
}

async function importBrews(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/brews', items);
    toast(t('settings.import.imported_brews').replace('${n}', r.imported), 'success');
    S.brews = await api('GET', '/api/brews');
    renderBrassins();
  } catch(e) { toast(t('settings.import.err_import_brews'), 'error'); }
  input.value = '';
}

async function exportDrafts() {
  const data = await api('GET', '/api/export/drafts');
  downloadJson(data, `brouillons_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_drafts'), 'success');
}

async function importDrafts(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/drafts', items);
    toast(t('settings.import.imported_drafts').replace('${n}', r.imported), 'success');
    S.drafts = await api('GET', '/api/drafts');
    renderBrouillons();
  } catch(e) { toast(t('settings.import.err_import_drafts'), 'error'); }
  input.value = '';
}

async function exportCalendar() {
  const data = await api('GET', '/api/export/calendar');
  downloadJson(data, `calendrier_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_cal'), 'success');
}

function downloadIcal() {
  const a = document.createElement('a');
  a.href = '/api/calendar/ics';
  a.download = `brewhome_${new Date().toISOString().slice(0,10)}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  toast(t('settings.import.exported_ical'), 'success');
}

async function copyIcalUrl() {
  const url = window.location.origin + '/api/calendar/ics';
  try {
    await navigator.clipboard.writeText(url);
    const icon = document.getElementById('ical-copy-icon');
    if (icon) { icon.className = 'fas fa-check'; setTimeout(() => { icon.className = 'fas fa-copy'; }, 1500); }
    toast(t('settings.import.ical_url_copied'), 'success');
  } catch(e) {
    document.getElementById('ical-url-input')?.select();
    toast(t('settings.import.ical_url_copied'), 'success');
  }
}

function openWebcal() {
  const url = (window.location.origin + '/api/calendar/ics').replace(/^https?:\/\//, 'webcal://');
  window.location.href = url;
}

async function importCalendar(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/calendar', items);
    toast(t('settings.import.imported_cal').replace('${n}', r.imported), 'success');
    S.customEvents = await api('GET', '/api/custom_events');
    renderCalendar();
  } catch(e) { toast(t('settings.import.err_import_cal'), 'error'); }
  input.value = '';
}

async function exportSpindles() {
  const data = await api('GET', '/api/export/spindles');
  downloadJson(data, `densimetres_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_spin'), 'success');
}

async function importSpindles(input) {
  const file = input.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  const items = Array.isArray(data) ? data : [data];
  try {
    const r = await api('POST', '/api/import/spindles', items);
    toast(t('settings.import.imported_spin').replace('${n}', r.imported), 'success');
    S.spindles = await api('GET', '/api/spindles');
    renderSpindles();
  } catch(e) { toast(t('settings.import.err_import_spin'), 'error'); }
  input.value = '';
}

function exportSettings() {
  const out = JSON.parse(JSON.stringify(appSettings));
  // Exclure les tokens GitHub et la clé IA (données sensibles)
  if (out.github?.vitrine) delete out.github.vitrine.pat;
  if (out.github?.data)    delete out.github.data.pat;
  if (out.ai)              delete out.ai.apiKey;
  downloadJson(out, `parametres_${new Date().toISOString().slice(0,10)}.json`);
  toast(t('settings.import.exported_settings'), 'success');
}

async function importSettings(input) {
  const file = input.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    // Fusionner sans écraser les tokens/clés existants (non inclus dans l'export)
    const githubBackup = appSettings.github;
    const aiKeyBackup  = appSettings.ai?.apiKey;
    Object.assign(appSettings, data);
    if (githubBackup) appSettings.github = githubBackup;
    if (aiKeyBackup && appSettings.ai) appSettings.ai.apiKey = aiKeyBackup;
    saveSettings();
    // Mettre à jour la DB pour les paramètres d'apparence
    if (data.appName != null || data.accentColor != null || data.appIcon != null) {
      await api('PUT', '/api/app-settings', {
        app_name:     appSettings.appName     || null,
        accent_color: appSettings.accentColor || null,
        app_icon:     appSettings.appIcon     || null,
      }).catch(() => {});
    }
    applyAppearance();
    renderSettingsWater();
    toast(t('settings.import.imported_settings'), 'success');
  } catch(e) { toast(t('settings.import.err_import_settings') + ' ' + e.message, 'error'); }
  input.value = '';
}

// ══════════════════════════════════════════════════════════════════════════════
// RESTORE FROM GIT
// ══════════════════════════════════════════════════════════════════════════════

function toggleRestoreAll(on) {
  document.querySelectorAll('#restore-git-sections input[type=checkbox]').forEach(cb => cb.checked = on);
}

async function restoreFromGit() {
  const sections = [...document.querySelectorAll('#restore-git-sections input[type=checkbox]:checked')]
    .map(cb => cb.value);
  if (!sections.length) { toast(t('settings.restore.err_no_section'), 'error'); return; }

  const modeEl = document.querySelector('input[name="restore-mode"]:checked');
  const mode   = modeEl ? modeEl.value : 'merge';

  if (mode === 'replace') {
    const labels = {
      inventaire: t('settings.import.inv_title'), recettes: t('settings.import.rec_title'),
      cave: t('settings.import.cave_title'), brassins: t('settings.import.brews_title'),
      catalogue: t('settings.import.catalog_title'), brouillons: t('settings.import.drafts_title'),
      calendrier: t('settings.import.cal_title'), densimetres: t('settings.import.spindles_title'),
    };
    const sectionNames = sections.map(s => labels[s] || s).join(', ');
    if (!await confirmModal(t('settings.restore.confirm_replace').replace('${sections}', sectionNames))) return;
  }

  const btn = document.getElementById('btn-restore-git');
  btn.disabled = true;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('settings.restore.fetching')}`;

  const resultsDiv = document.getElementById('restore-git-results');
  resultsDiv.innerHTML = '';
  resultsDiv.style.display = 'none';

  try {
    const res = await api('POST', '/api/restore/git', { sections, mode });
    const results = res.results || {};
    const chips = [];
    let anyError = false;

    for (const [sec, r] of Object.entries(results)) {
      const labels = {
        inventaire: t('settings.import.inv_title'), recettes: t('settings.import.rec_title'),
        cave: t('settings.import.cave_title'), brassins: t('settings.import.brews_title'),
        catalogue: t('settings.import.catalog_title'), brouillons: t('settings.import.drafts_title'),
        calendrier: t('settings.import.cal_title'), densimetres: t('settings.import.spindles_title'),
      };
      const label = labels[sec] || sec;
      if (r.error) {
        anyError = true;
        const errMsg = r.error === 'not_found' ? t('settings.restore.err_not_found') : r.error;
        chips.push(`<span style="background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);border-radius:6px;padding:3px 8px;color:var(--danger)">❌ ${label}: ${errMsg}</span>`);
      } else {
        chips.push(`<span style="background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.25);border-radius:6px;padding:3px 8px;color:#22d3ee">✓ ${label}: ${r.count}</span>`);
      }
    }

    resultsDiv.innerHTML = chips.join('');
    resultsDiv.style.display = 'flex';

    // Reload affected data in memory
    const reloads = [];
    if (results.inventaire && !results.inventaire.error) reloads.push(api('GET', '/api/inventory').then(d => { S.inventory = d; renderInventaire(); }));
    if (results.recettes   && !results.recettes.error)   reloads.push(api('GET', '/api/recipes').then(d => { S.recipes = d; renderRecipeList(); }));
    if (results.cave       && !results.cave.error)       reloads.push(api('GET', '/api/beers').then(d => { S.beers = d; renderCave(); }));
    if (results.brassins   && !results.brassins.error)   reloads.push(api('GET', '/api/brews').then(d => { S.brews = d; renderBrassins(); }));
    if (results.catalogue  && !results.catalogue.error)  reloads.push(api('GET', '/api/catalog').then(d => { S.catalog = d; }));
    if (results.brouillons && !results.brouillons.error) reloads.push(api('GET', '/api/drafts').then(d => { S.drafts = d; renderBrouillons(); }));
    if (results.calendrier && !results.calendrier.error) reloads.push(api('GET', '/api/custom_events').then(d => { S.customEvents = d; renderCalendar(); }));
    if (results.densimetres && !results.densimetres.error) reloads.push(api('GET', '/api/spindles').then(d => { S.spindles = d; renderSpindles(); }));
    await Promise.allSettled(reloads);

    if (!anyError) toast(t('settings.restore.success'), 'success');
    else           toast(t('settings.restore.partial'), 'warn');
  } catch(e) {
    if (e.message && e.message.includes('no_target')) {
      toast(t('settings.restore.err_no_target'), 'error');
    } else {
      toast(t('settings.restore.err_fetch') + ' ' + (e.message || ''), 'error');
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-cloud-arrow-down"></i> ${t('settings.restore.btn_restore')}`;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// DB ADMIN
// ══════════════════════════════════════════════════════════════════════════════

async function loadDbStats() {
  const loading = document.getElementById('dbadmin-loading');
  const content = document.getElementById('dbadmin-content');
  if (loading) loading.style.display = '';
  if (content) content.style.display = 'none';
  try {
    const data = await api('GET', '/api/admin/db-stats');
    const fmt = b => b >= 1048576 ? (b/1048576).toFixed(2)+' Mo' : (b/1024).toFixed(1)+' Ko';
    const mainTotal = Object.values(data.main.tables).reduce((a,b)=>a+b, 0);
    const readTotal = Object.values(data.readings.tables).reduce((a,b)=>a+b, 0);
    document.getElementById('dbadmin-summary').innerHTML = `
      <div class="stat"><div class="stat-val" style="color:var(--info)">${fmt(data.main.size)}</div><div class="stat-lbl">${t('dbadmin.main_size')}</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--info)">${fmt(data.readings.size)}</div><div class="stat-lbl">${t('dbadmin.readings_size')}</div></div>
      <div class="stat"><div class="stat-val">${fmt(data.main.size + data.readings.size)}</div><div class="stat-lbl">${t('dbadmin.total_size')}</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--success)">${(mainTotal + readTotal).toLocaleString()}</div><div class="stat-lbl">${t('dbadmin.total_rows')}</div></div>`;
    const renderTbl = (tables, id) => {
      const rows = Object.entries(tables).sort((a,b) => b[1]-a[1]);
      document.getElementById(id).innerHTML = rows.map(([name, count]) =>
        `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)">
          <span style="font-size:.82rem;font-family:monospace;color:var(--text)">${name}</span>
          <span class="nav-badge">${count.toLocaleString()}</span>
        </div>`
      ).join('');
    };
    renderTbl(data.main.tables, 'dbadmin-main-tables');
    renderTbl(data.readings.tables, 'dbadmin-readings-tables');
    if (loading) loading.style.display = 'none';
    if (content) content.style.display = '';
  } catch(e) {
    if (loading) loading.innerHTML = `<i class="fas fa-triangle-exclamation"></i><p>${esc(e.message||'Error')}</p>`;
  }
}

async function runVacuum() {
  const btn = document.getElementById('dbadmin-vacuum-btn');
  btn.disabled = true;
  const orig = btn.innerHTML;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('dbadmin.vacuuming')}`;
  try {
    await api('POST', '/api/admin/vacuum');
    toast(t('dbadmin.vacuum_done'), 'success');
    await loadDbStats();
  } catch(e) {
    toast(t('dbadmin.vacuum_error'), 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

function exportSql() {
  const a = document.createElement('a');
  a.href = '/api/admin/export-sql';
  a.download = `brewhome_${new Date().toISOString().slice(0,10)}.sql`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  toast(t('dbadmin.exported_sql'), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// WATER CORRECTION
// ══════════════════════════════════════════════════════════════════════════════

// mg of each ion contributed per gram of mineral added to 1 L
const WC_MINERAL_FX = {
  'Sulfate de calcium':    { ca: 232.8, mg: 0,    na: 0,     so4: 557.9,  cl: 0,     hco3: 0      },
  'Sulfate de magnésium':  { ca: 0,     mg: 98.6, na: 0,     so4: 389.8,  cl: 0,     hco3: 0      },
  'Chlorure de calcium':   { ca: 361.2, mg: 0,    na: 0,     so4: 0,      cl: 638.9, hco3: 0      },
  'Chlorure de sodium':    { ca: 0,     mg: 0,    na: 393.3, so4: 0,      cl: 606.5, hco3: 0      },
  'Carbonate de calcium':  { ca: 400.4, mg: 0,    na: 0,     so4: 0,      cl: 0,     hco3: 1218.0 },
  'Bicarbonate de sodium': { ca: 0,     mg: 0,    na: 273.7, so4: 0,      cl: 0,     hco3: 726.4  },
};

const WC_MINERAL_LABEL = {
  'Sulfate de calcium':    'Sulfate de calcium (CaSO₄)',
  'Sulfate de magnésium':  'Sulfate de magnésium (MgSO₄)',
  'Chlorure de calcium':   'Chlorure de calcium (CaCl₂)',
  'Chlorure de sodium':    'Chlorure de sodium (NaCl)',
  'Carbonate de calcium':  'Carbonate de calcium (CaCO₃)',
  'Bicarbonate de sodium': 'Bicarbonate de sodium (NaHCO₃)',
};

// mL of acid needed to neutralize 1 mEq of total alkalinity
// mEq_total = Δ_HCO3_ppm * volume_L / 61.0
const WC_ACID_FX = {
  'Acide lactique 80%':     0.09306,
  'Acide lactique 88%':     0.08461,
  'Acide phosphorique 75%': 0.08277,
  'Acide phosphorique 85%': 0.06826,
};

// Classic water profiles (mg/L)
const WC_PRESETS = {
  neutre:    { ca: 0,   mg: 0,  na: 0,  so4: 0,   cl: 0,   hco3: 0   },
  pilsen:    { ca: 7,   mg: 3,  na: 2,  so4: 5,   cl: 5,   hco3: 15  },
  lager:     { ca: 50,  mg: 8,  na: 10, so4: 50,  cl: 60,  hco3: 100 },
  weizen:    { ca: 50,  mg: 10, na: 10, so4: 30,  cl: 55,  hco3: 150 },
  equilibre: { ca: 75,  mg: 5,  na: 25, so4: 75,  cl: 75,  hco3: 50  },
  paleale:   { ca: 100, mg: 8,  na: 10, so4: 150, cl: 80,  hco3: 30  },
  amber:     { ca: 75,  mg: 10, na: 20, so4: 80,  cl: 80,  hco3: 100 },
  saison:    { ca: 75,  mg: 10, na: 15, so4: 100, cl: 50,  hco3: 60  },
  ipa:       { ca: 150, mg: 10, na: 10, so4: 300, cl: 55,  hco3: 0   },
  neipa:     { ca: 100, mg: 5,  na: 15, so4: 50,  cl: 200, hco3: 0   },
  stout:     { ca: 100, mg: 10, na: 35, so4: 50,  cl: 75,  hco3: 300 },
};

function toggleWaterCorrection() {
  const panel = document.getElementById('rec-wc-panel');
  const btn   = document.getElementById('btn-wc');
  const open  = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : '';
  btn.classList.toggle('open', !open);
  if (!open) renderWaterCorrection();
}

// ── Gestionnaire de profils eau (onglet Paramètres → Eau) ────────────────────

const _WC_ION_META = [
  { k: 'ph',   label: 'pH',       unit: '',     step: 0.1,  max: 14  },
  { k: 'ca',   label: 'Ca²⁺',    unit: 'mg/L', step: 1,    max: 500 },
  { k: 'mg',   label: 'Mg²⁺',    unit: 'mg/L', step: 1,    max: 200 },
  { k: 'na',   label: 'Na⁺',     unit: 'mg/L', step: 1,    max: 300 },
  { k: 'so4',  label: 'SO₄²⁻',  unit: 'mg/L', step: 1,    max: 800 },
  { k: 'cl',   label: 'Cl⁻',    unit: 'mg/L', step: 1,    max: 400 },
  { k: 'hco3', label: 'HCO₃⁻',  unit: 'mg/L', step: 1,    max: 600 },
];

function renderWaterProfilesManager() {
  const el = document.getElementById('wc-profiles-manager');
  if (!el) return;
  const profiles = appSettings.waterProfiles || [];
  if (!profiles.length) {
    el.innerHTML = `<p style="font-size:.82rem;color:var(--muted);padding:4px 0" data-i18n="settings.water.profile_empty">${t('settings.water.profile_empty')}</p>`;
    return;
  }
  el.innerHTML = profiles.map((p, idx) => {
    const summary = _WC_ION_META
      .filter(m => p[m.k] != null)
      .map(m => `<span style="color:var(--muted)">${m.label}</span> <strong>${p[m.k]}${m.unit ? ' ' + m.unit : ''}</strong>`)
      .join(' &thinsp;·&thinsp; ');
    return `
    <div class="wc-profile-row" id="wcp-row-${p.id}" style="padding:10px 12px;background:var(--card2);border-radius:8px;margin-bottom:6px">
      <div class="wcp-display" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="font-weight:600;font-size:.88rem;flex:1;min-width:100px">${esc(p.name)}</span>
        <span style="font-size:.72rem;padding:1px 7px;border-radius:10px;background:${p.isSource ? 'rgba(59,130,246,.15)' : 'rgba(99,102,241,.15)'};color:${p.isSource ? 'var(--info)' : 'var(--accent)'};white-space:nowrap">${p.isSource ? t('settings.water.profile_role_source') : t('settings.water.profile_role_target')}</span>
        <span style="font-size:.78rem;flex:3;min-width:180px;line-height:1.7">${summary || `<span style="color:var(--muted);font-style:italic">${t('settings.water.profile_no_values')}</span>`}</span>
        <span style="display:flex;gap:5px;flex-shrink:0">
          <button class="btn btn-icon btn-sm btn-ghost" onclick="editWaterProfile('${p.id}')" title="${t('common.edit')}"><i class="fas fa-pencil"></i></button>
          <button class="btn btn-icon btn-sm btn-ghost" style="color:var(--danger)" onclick="deleteWaterProfileFromSettings('${p.id}')" title="${t('common.delete')}"><i class="fas fa-trash-can"></i></button>
        </span>
      </div>
      <div class="wcp-edit" style="display:none;margin-top:10px">
        <div class="field" style="margin-bottom:8px">
          <label style="font-size:.78rem;font-weight:600">${t('settings.water.profile_name')}</label>
          <input type="text" id="wcp-name-${p.id}" value="${esc(p.name)}" style="width:100%;max-width:300px"
            onkeydown="if(event.key==='Enter')saveWaterProfileEdit('${p.id}');if(event.key==='Escape')cancelWaterProfileEdit('${p.id}')">
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px">
          ${_WC_ION_META.map(m => `
          <div class="field" style="margin:0">
            <label style="font-size:.72rem">${m.label}${m.unit ? ' (' + m.unit + ')' : ''}</label>
            <input type="number" id="wcp-${m.k}-${p.id}" value="${p[m.k] != null ? p[m.k] : ''}"
              min="0" max="${m.max}" step="${m.step}" style="text-align:center">
          </div>`).join('')}
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm btn-primary" onclick="saveWaterProfileEdit('${p.id}')"><i class="fas fa-check"></i> ${t('common.save')}</button>
          <button class="btn btn-sm btn-ghost" onclick="cancelWaterProfileEdit('${p.id}')">${t('common.cancel')}</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

function editWaterProfile(id) {
  // Fermer les autres éditions ouvertes
  document.querySelectorAll('.wcp-edit').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.wcp-display').forEach(el => el.style.display = 'flex');
  const row = document.getElementById(`wcp-row-${id}`);
  if (!row) return;
  row.querySelector('.wcp-display').style.display = 'none';
  row.querySelector('.wcp-edit').style.display    = 'block';
  row.querySelector(`#wcp-name-${id}`)?.focus();
}

function cancelWaterProfileEdit(id) {
  const row = document.getElementById(`wcp-row-${id}`);
  if (!row) return;
  row.querySelector('.wcp-display').style.display = 'flex';
  row.querySelector('.wcp-edit').style.display    = 'none';
}

function saveWaterProfileEdit(id) {
  const nameEl = document.getElementById(`wcp-name-${id}`);
  const name   = nameEl?.value.trim();
  if (!name) { nameEl?.focus(); return; }
  const idx = (appSettings.waterProfiles || []).findIndex(p => p.id === id);
  if (idx === -1) return;
  const readV = k => { const v = parseFloat(document.getElementById(`wcp-${k}-${id}`)?.value); return isNaN(v) ? null : v; };
  appSettings.waterProfiles[idx] = {
    ...appSettings.waterProfiles[idx],
    name,
    ..._WC_ION_META.reduce((acc, m) => { acc[m.k] = readV(m.k); return acc; }, {}),
  };
  _syncSettingsToServer();
  renderWaterProfilesManager();
  renderWaterProfileButtons();
  toast(t('rec.wc_profile_saved').replace('${name}', name), 'success');
}

function deleteWaterProfileFromSettings(id) {
  if (!appSettings.waterProfiles) return;
  appSettings.waterProfiles = appSettings.waterProfiles.filter(p => p.id !== id);
  _syncSettingsToServer();
  renderWaterProfilesManager();
  renderWaterProfileButtons();
}

function addWaterProfileFromSettings() {
  if (!appSettings.waterProfiles) appSettings.waterProfiles = [];
  const newProfile = {
    id:   Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
    name: t('settings.water.profile_new_default'),
    isSource: true,
    ph: null, ca: null, mg: null, na: null, so4: null, cl: null, hco3: null,
  };
  appSettings.waterProfiles.push(newProfile);
  renderWaterProfilesManager();
  // Ouvrir directement en mode édition
  setTimeout(() => editWaterProfile(newProfile.id), 0);
}

// ── Sélecteur d'eau source (per-recette) ─────────────────────────────────────

function renderWcSourceSelector() {
  const el = document.getElementById('wc-source-btns');
  if (!el) return;
  const profiles    = (appSettings.waterProfiles || []).filter(p => p.isSource);
  const selectedId  = _wcSourceProfile?.id || null;
  const isDefault   = selectedId === null;
  const communeName = appSettings.hubeau?.communeName;
  const defLabel    = communeName
    ? `${communeName} <span style="font-size:.72rem;opacity:.7">(${t('rec.wc_source_default')})</span>`
    : t('rec.wc_source_default');

  const defBtn = `<button class="btn btn-sm ${isDefault ? 'btn-primary' : 'btn-ghost'}"
    onclick="selectWcSource(null)">${defLabel}</button>`;

  const profBtns = profiles.map(p =>
    `<button class="btn btn-sm ${selectedId === p.id ? 'btn-primary' : 'btn-ghost'}"
      onclick="selectWcSource('${p.id}')">${esc(p.name)}</button>`
  ).join('');

  el.innerHTML = defBtn + profBtns;
}

function selectWcSource(id) {
  _wcSourceProfile = id === null
    ? null
    : (appSettings.waterProfiles || []).find(p => p.id === id) || null;
  renderWcSourceSelector();
  _renderWcSourceDisplay();
  calcWaterCorrection();
}

function _renderWcSourceDisplay() {
  const srcEl = document.getElementById('wc-source-display');
  if (!srcEl) return;
  const w      = _wcSourceProfile || appSettings.water || {};
  const hasSrc = ['ca','mg','na','so4','cl','hco3'].some(k => w[k] != null && w[k] !== '');
  if (!hasSrc) {
    const hint = _wcSourceProfile
      ? `<span style="color:var(--amber)"><i class="fas fa-triangle-exclamation"></i> ${t('rec.wc_profile_no_values')}</span>`
      : `<span style="color:var(--danger)"><i class="fas fa-triangle-exclamation"></i> ${t('rec.wc_no_profile')}</span>`;
    srcEl.innerHTML = hint;
    return;
  }
  const fmt = (v, u) => `<strong>${parseFloat(v) || 0}</strong><span style="color:var(--muted);font-size:.72rem"> ${u}</span>`;
  srcEl.innerHTML = [
    `pH ${fmt(w.ph, '')}`,
    `Ca²⁺ ${fmt(w.ca, 'mg/L')}`,
    `Mg²⁺ ${fmt(w.mg, 'mg/L')}`,
    `Na⁺ ${fmt(w.na, 'mg/L')}`,
    `SO₄²⁻ ${fmt(w.so4, 'mg/L')}`,
    `Cl⁻ ${fmt(w.cl, 'mg/L')}`,
    `HCO₃⁻ ${fmt(w.hco3, 'mg/L')}`,
  ].join(' &nbsp;·&nbsp; ');
}

function renderWaterProfileButtons() {
  const el = document.getElementById('wc-custom-profiles');
  if (!el) return;
  const profiles = (appSettings.waterProfiles || []).filter(p => !p.isSource);
  if (!profiles.length) { el.innerHTML = ''; return; }
  el.innerHTML = profiles.map(p =>
    `<span style="display:inline-flex;align-items:center;gap:0">
       <button class="btn btn-ghost btn-sm" style="border-radius:6px 0 0 6px;padding-right:6px"
         onclick="loadWaterProfile('${p.id}')">${esc(p.name)}</button>
       <button class="btn btn-ghost btn-sm" style="border-radius:0 6px 6px 0;padding:4px 6px;color:var(--muted)"
         onclick="deleteWaterProfile('${p.id}')" title="${t('common.delete')}"><i class="fas fa-xmark" style="font-size:.7rem"></i></button>
     </span>`
  ).join('');
}

function loadWaterProfile(id) {
  const p = (appSettings.waterProfiles || []).find(x => x.id === id);
  if (!p) return;
  ['ca','mg','na','so4','cl','hco3'].forEach(k => {
    const el = document.getElementById(`wc-t-${k}`);
    if (el && p[k] != null) el.value = p[k]; else if (el) el.value = '';
  });
  const phEl = document.getElementById('wc-t-ph');
  if (phEl) phEl.value = p.ph != null ? p.ph : '';
  calcWaterCorrection();
}

function startSaveWaterProfile() {
  const btn  = document.getElementById('wc-add-profile-btn');
  const form = document.getElementById('wc-save-profile-form');
  if (btn)  btn.style.display  = 'none';
  if (form) { form.style.display = 'flex'; document.getElementById('wc-profile-name')?.focus(); }
}

function cancelSaveWaterProfile() {
  const btn  = document.getElementById('wc-add-profile-btn');
  const form = document.getElementById('wc-save-profile-form');
  if (btn)  btn.style.display  = '';
  if (form) form.style.display = 'none';
  const nameEl = document.getElementById('wc-profile-name');
  if (nameEl) nameEl.value = '';
}

function saveWaterProfile() {
  const nameEl = document.getElementById('wc-profile-name');
  const name   = nameEl?.value.trim();
  if (!name) { nameEl?.focus(); return; }
  const readV = id => { const v = parseFloat(document.getElementById(id)?.value); return isNaN(v) ? null : v; };
  const profile = {
    id:   Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
    name, isSource: false,
    ca:   readV('wc-t-ca'),  mg:   readV('wc-t-mg'),  na:   readV('wc-t-na'),
    so4:  readV('wc-t-so4'), cl:   readV('wc-t-cl'),  hco3: readV('wc-t-hco3'),
    ph:   readV('wc-t-ph'),
  };
  if (!appSettings.waterProfiles) appSettings.waterProfiles = [];
  appSettings.waterProfiles.push(profile);
  _syncSettingsToServer();
  cancelSaveWaterProfile();
  renderWaterProfileButtons();
  toast(t('rec.wc_profile_saved').replace('${name}', name), 'success');
}

function deleteWaterProfile(id) {
  if (!appSettings.waterProfiles) return;
  appSettings.waterProfiles = appSettings.waterProfiles.filter(p => p.id !== id);
  _syncSettingsToServer();
  renderWaterProfileButtons();
  renderWaterProfilesManager();
}

function renderWaterCorrection() {
  renderWcSourceSelector();
  _renderWcSourceDisplay();
  // Auto-fill volumes if empty: prefer recipe suggestion, fall back to display elements
  const mashEl   = document.getElementById('wc-volume-mash');
  const spargeEl = document.getElementById('wc-volume-sparge');
  if (window._wcSugg) {
    if (mashEl   && !mashEl.value)   mashEl.value   = window._wcSugg.mash.toFixed(1);
    if (spargeEl && !spargeEl.value) spargeEl.value = window._wcSugg.sparge.toFixed(1);
  } else {
    if (mashEl && !mashEl.value) {
      const v = parseFloat(document.getElementById('rw-mash')?.textContent);
      if (!isNaN(v)) mashEl.value = v.toFixed(1);
    }
    if (spargeEl && !spargeEl.value) {
      const v = parseFloat(document.getElementById('rw-sparge')?.textContent);
      if (!isNaN(v)) spargeEl.value = v.toFixed(1);
    }
  }
  if (typeof _updateWcSuggRow === 'function') _updateWcSuggRow();
  renderWaterProfileButtons();
  calcWaterCorrection();
}

function wcPreset(name) {
  const p = WC_PRESETS[name];
  if (!p) return;
  ['ca','mg','na','so4','cl','hco3'].forEach(k => {
    const el = document.getElementById(`wc-t-${k}`);
    if (el) el.value = p[k];
  });
  calcWaterCorrection();
}

// Non-negative least squares via coordinate descent (Gauss-Seidel).
// Minimises Σ_i W[i]·(Σ_j A[i][j]·x[j] − b[i])²  subject to  x[j] ≥ 0.
// Converges in < 30 iterations for the 6×6 mineral/ion system.
function _nnls(A, b, W) {
  const m = A.length, n = A[0].length;
  const x = new Float64Array(n);
  // Pre-compute weighted normal-equation matrices  AtWA  and  AtWb
  const AtWA = Array.from({length: n}, () => new Float64Array(n));
  const AtWb = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    for (let k = 0; k < n; k++) {
      let s = 0;
      for (let i = 0; i < m; i++) s += W[i] * A[i][j] * A[i][k];
      AtWA[j][k] = s;
    }
    let s = 0;
    for (let i = 0; i < m; i++) s += W[i] * A[i][j] * b[i];
    AtWb[j] = s;
  }
  // Coordinate descent: optimise each variable in turn, projected to ≥ 0
  for (let iter = 0; iter < 500; iter++) {
    let maxDelta = 0;
    for (let j = 0; j < n; j++) {
      if (AtWA[j][j] < 1e-12) continue;
      let num = AtWb[j];
      for (let k = 0; k < n; k++) if (k !== j) num -= AtWA[j][k] * x[k];
      const xNew = Math.max(0, num / AtWA[j][j]);
      maxDelta = Math.max(maxDelta, Math.abs(xNew - x[j]));
      x[j] = xNew;
    }
    if (maxDelta < 1e-9) break;
  }
  return x;
}

function _computeWCDoses(vol, s, t) {
  const IONS     = ['ca','mg','na','so4','cl','hco3'];
  // Column order must stay in sync with the xPerL index references below
  const MINERALS = ['Sulfate de calcium','Sulfate de magnésium','Chlorure de calcium',
                    'Chlorure de sodium','Carbonate de calcium','Bicarbonate de sodium'];

  const delta = {};
  IONS.forEach(k => { delta[k] = t[k] !== null ? t[k] - s[k] : 0; });

  // Target vector: positive deficits only; inactive ions → 0
  const b = IONS.map(k => t[k] !== null ? Math.max(0, delta[k]) : 0);
  // Weight: 1 for active (targeted) ions, 0 for unset ions
  const W = IONS.map(k => t[k] !== null ? 1 : 0);
  // Effect matrix A[ion][mineral] = mg/L per g/L
  const A = IONS.map(ion => MINERALS.map(min => WC_MINERAL_FX[min][ion]));

  // Solve  min ||W·(A·x − b)||²,  x ≥ 0
  const xPerL = _nnls(A, b, W);   // doses in g/L

  // Convert per-litre doses to total grams for this volume
  const doses = {};
  MINERALS.forEach((min, j) => { doses[min] = xPerL[j] * vol; });

  // Acid for HCO3 reduction (source alkalinity above target)
  const hco3Excess = t.hco3 !== null ? Math.max(0, s.hco3 - t.hco3) : 0;
  const acidDoses = {};
  if (hco3Excess > 0) {
    const totalMeq = hco3Excess * vol / 61.0;
    Object.entries(WC_ACID_FX).forEach(([acid, mlPerMeq]) => {
      acidDoses[acid] = totalMeq * mlPerMeq;
    });
  }

  // Resulting ion concentrations after mineral additions
  const result = { ...s };
  MINERALS.forEach((min, j) => {
    if (xPerL[j] <= 0) return;
    const fx = WC_MINERAL_FX[min];
    IONS.forEach(k => { result[k] += xPerL[j] * fx[k]; });
  });
  if (hco3Excess > 0) result.hco3 = Math.max(0, result.hco3 - hco3Excess);

  // Alternative CaCl2 : same Ca as CaSO4 provides, but via Cl instead of SO4
  const caFromCaSO4    = xPerL[0] * WC_MINERAL_FX['Sulfate de calcium'].ca;
  const altCaCl2g      = caFromCaSO4 > 0.5 ? (caFromCaSO4 / WC_MINERAL_FX['Chlorure de calcium'].ca) * vol : 0;

  // Alternative CaCO3 : same HCO3 as NaHCO3 provides, but adds Ca instead of Na
  const hco3FromNaHCO3 = xPerL[5] * WC_MINERAL_FX['Bicarbonate de sodium'].hco3;
  const altCaCO3g      = hco3FromNaHCO3 > 0.5 ? (hco3FromNaHCO3 / WC_MINERAL_FX['Carbonate de calcium'].hco3) * vol : 0;

  // Alternative NaHCO3 : same HCO3 as CaCO3 provides, but adds Na instead of Ca
  const hco3FromCaCO3  = xPerL[4] * WC_MINERAL_FX['Carbonate de calcium'].hco3;
  const altNaHCO3g     = hco3FromCaCO3 > 0.5 ? (hco3FromCaCO3 / WC_MINERAL_FX['Bicarbonate de sodium'].hco3) * vol : 0;

  return { delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g };
}

function calcWaterCorrection() {
  const volMash   = parseFloat(document.getElementById('wc-volume-mash')?.value)   || 0;
  const volSparge = parseFloat(document.getElementById('wc-volume-sparge')?.value) || 0;

  const w = _wcSourceProfile || appSettings.water || {};
  const s = { ca: parseFloat(w.ca)||0, mg: parseFloat(w.mg)||0, na: parseFloat(w.na)||0,
               so4: parseFloat(w.so4)||0, cl: parseFloat(w.cl)||0, hco3: parseFloat(w.hco3)||0 };

  const readT = id => { const v = parseFloat(document.getElementById(id)?.value); return isNaN(v) ? null : v; };
  const tgt = { ca: readT('wc-t-ca'), mg: readT('wc-t-mg'), na: readT('wc-t-na'),
                so4: readT('wc-t-so4'), cl: readT('wc-t-cl'), hco3: readT('wc-t-hco3'),
                ph: readT('wc-t-ph') };

  const hasTarget = ['ca','mg','na','so4','cl','hco3'].some(k => tgt[k] !== null);
  const resMash   = document.getElementById('wc-results-mash');
  const resSparge = document.getElementById('wc-results-sparge');

  if (!hasTarget) {
    if (resMash)   resMash.style.display   = 'none';
    if (resSparge) resSparge.style.display = 'none';
    return;
  }

  if (volMash > 0) {
    const { delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g } = _computeWCDoses(volMash, s, tgt);
    _renderWCResults(s, tgt, delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g, 'wc-results-mash', t('rec.wc_mash'), 'empatage');
  } else if (resMash) resMash.style.display = 'none';

  if (volSparge > 0) {
    const { delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g } = _computeWCDoses(volSparge, s, tgt);
    _renderWCResults(s, tgt, delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g, 'wc-results-sparge', t('rec.wc_sparge'), 'sparge');
  } else if (resSparge) resSparge.style.display = 'none';
}

function _renderWCResults(s, tgt, delta, doses, acidDoses, result, altCaCl2g, altCaCO3g, altNaHCO3g, containerId, label, suffix) {
  const otherType = suffix === 'empatage' ? 'empatage' : 'sparge';
  const ION_META = [
    { k: 'ca',   label: t('rec.wc_ca')   },
    { k: 'mg',   label: t('rec.wc_mg')   },
    { k: 'na',   label: t('rec.wc_na')   },
    { k: 'so4',  label: t('rec.wc_so4')  },
    { k: 'cl',   label: t('rec.wc_cl')   },
    { k: 'hco3', label: t('rec.wc_hco3') },
  ];

  // ── Ion balance table ──
  let html = `
    <div style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--info);margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid rgba(255,255,255,.08)">
      <i class="fas fa-droplet"></i> ${label}
    </div>
    <div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px">${t('rec.wc_ion_balance')}</div>
    <div style="overflow-x:auto;margin-bottom:14px">
    <table style="width:100%;font-size:.8rem;border-collapse:collapse;min-width:380px">
      <thead><tr style="color:var(--muted);border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:3px 8px">${t('rec.wc_col_ion')}</th>
        <th style="text-align:right;padding:3px 8px">${t('rec.wc_col_source')}</th>
        <th style="text-align:right;padding:3px 8px">${t('rec.wc_col_target')}</th>
        <th style="text-align:right;padding:3px 8px">Δ</th>
        <th style="text-align:right;padding:3px 8px">${t('rec.wc_col_result')}</th>
      </tr></thead><tbody>`;

  ION_META.forEach(({ k, label }) => {
    const src = s[k] ?? 0;
    const ionTgt = tgt[k];
    const res = result[k] ?? 0;
    const hasTgt = ionTgt !== null;
    const d = hasTgt ? delta[k] : null;
    const dStr  = d === null ? '–' : (d >= 0 ? `+${d.toFixed(0)}` : d.toFixed(0));
    const dCol  = d === null ? '' : d > 0 ? 'color:var(--info)' : d < 0 ? 'color:var(--danger)' : '';
    const diff  = hasTgt ? Math.abs(res - ionTgt) : null;
    const resCol= diff === null ? '' : diff < 5 ? 'color:var(--success)' : diff < 15 ? 'color:var(--amber)' : 'color:var(--danger)';
    // Warning when source already exceeds target
    const exceeded = hasTgt && ionTgt !== null && src > ionTgt + 1;
    html += `
      <tr style="border-bottom:1px solid var(--border)22">
        <td style="padding:3px 8px;font-weight:600">${label}</td>
        <td style="text-align:right;padding:3px 8px">${src.toFixed(0)}</td>
        <td style="text-align:right;padding:3px 8px">${hasTgt ? ionTgt.toFixed(0) : '–'}</td>
        <td style="text-align:right;padding:3px 8px;${dCol}">${dStr}${exceeded ? ` <i class="fas fa-circle-exclamation" style="color:var(--amber);font-size:.7rem" title="${t('rec.wc_src_exceeds')}"></i>` : ''}</td>
        <td style="text-align:right;padding:3px 8px;font-weight:700;${resCol}">${res.toFixed(1)}</td>
      </tr>`;
  });

  // SO4/Cl ratio
  const ratioVal  = (result.cl > 0) ? result.so4 / result.cl : result.so4;
  const ratioLbl  = ratioVal > 2 ? t('rec.wc_hop_fav') : ratioVal < 0.5 ? t('rec.wc_malt_fav') : t('rec.wc_balanced');
  const ratioCol  = ratioVal > 2 ? 'var(--hop)' : ratioVal < 0.5 ? 'var(--malt)' : 'var(--success)';
  html += `
    <tr style="border-top:1px solid var(--border);background:rgba(255,255,255,.03)">
      <td colspan="4" style="padding:3px 8px;font-size:.74rem;color:var(--muted)">${t('rec.wc_ratio')}</td>
      <td style="text-align:right;padding:3px 8px;font-weight:700;color:${ratioCol}">${ratioVal.toFixed(2)} — ${ratioLbl}</td>
    </tr>`;
  html += `</tbody></table></div>`;

  // ── Mineral doses ──
  const activeMinerals = Object.entries(doses).filter(([, g]) => g >= 0.05);
  html += `<div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px"><i class="fas fa-flask"></i> ${t('rec.wc_minerals')}</div>`;
  if (!activeMinerals.length) {
    html += `<p style="font-size:.8rem;color:var(--muted);font-style:italic;margin-bottom:12px">${t('rec.wc_no_minerals')}</p>`;
  } else {
    html += `<div style="display:flex;flex-direction:column;gap:5px;margin-bottom:14px">`;
    activeMinerals.forEach(([mineral, grams]) => {
      html += `
        <div style="display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:5px 10px">
          <span style="flex:1;font-size:.83rem">${WC_MINERAL_LABEL[mineral] || mineral}</span>
          <span style="font-weight:700;color:var(--amber);min-width:58px;text-align:right">${grams.toFixed(2)} g</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 8px;white-space:nowrap"
            onclick="wcAddToRecipe('${mineral} (${suffix})',${grams.toFixed(2)},'g','${otherType}')">
            <i class="fas fa-plus"></i> ${t('rec.wc_add_recipe')}
          </button>
        </div>`;
    });
    html += `</div>`;
  }

  // ── Alternative CaCl2 ──
  if (altCaCl2g >= 0.05) {
    html += `
      <div style="margin-bottom:14px">
        <div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber);margin-bottom:6px">
          <i class="fas fa-shuffle"></i> ${t('rec.wc_alt_cacl2')}
        </div>
        <div style="color:var(--muted);font-size:.78rem;margin-bottom:6px;font-style:italic">
          ${t('rec.wc_alt_cacl2_desc')}
        </div>
        <div style="display:flex;align-items:center;gap:8px;background:var(--card);border:1px dashed var(--border);border-radius:6px;padding:5px 10px">
          <span style="flex:1;font-size:.83rem">${WC_MINERAL_LABEL['Chlorure de calcium']}</span>
          <span style="font-weight:700;color:var(--amber);min-width:58px;text-align:right">${altCaCl2g.toFixed(2)} g</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 8px;white-space:nowrap"
            onclick="wcAddToRecipe('Chlorure de calcium (${suffix})',${altCaCl2g.toFixed(2)},'g','${otherType}')">
            <i class="fas fa-plus"></i> ${t('rec.wc_add_recipe')}
          </button>
        </div>
      </div>`;
  }

  // ── Alternative CaCO3 ──
  if (altCaCO3g >= 0.05) {
    html += `
      <div style="margin-bottom:14px">
        <div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber);margin-bottom:6px">
          <i class="fas fa-shuffle"></i> ${t('rec.wc_alt_caco3')}
        </div>
        <div style="color:var(--muted);font-size:.78rem;margin-bottom:6px;font-style:italic">
          ${t('rec.wc_alt_caco3_desc')}
        </div>
        <div style="display:flex;align-items:center;gap:8px;background:var(--card);border:1px dashed var(--border);border-radius:6px;padding:5px 10px">
          <span style="flex:1;font-size:.83rem">${WC_MINERAL_LABEL['Carbonate de calcium']}</span>
          <span style="font-weight:700;color:var(--amber);min-width:58px;text-align:right">${altCaCO3g.toFixed(2)} g</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 8px;white-space:nowrap"
            onclick="wcAddToRecipe('Carbonate de calcium (${suffix})',${altCaCO3g.toFixed(2)},'g','${otherType}')">
            <i class="fas fa-plus"></i> ${t('rec.wc_add_recipe')}
          </button>
        </div>
      </div>`;
  }

  // ── Alternative NaHCO3 ──
  if (altNaHCO3g >= 0.05) {
    html += `
      <div style="margin-bottom:14px">
        <div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber);margin-bottom:6px">
          <i class="fas fa-shuffle"></i> ${t('rec.wc_alt_nahco3')}
        </div>
        <div style="color:var(--muted);font-size:.78rem;margin-bottom:6px;font-style:italic">
          ${t('rec.wc_alt_nahco3_desc')}
        </div>
        <div style="display:flex;align-items:center;gap:8px;background:var(--card);border:1px dashed var(--border);border-radius:6px;padding:5px 10px">
          <span style="flex:1;font-size:.83rem">${WC_MINERAL_LABEL['Bicarbonate de sodium']}</span>
          <span style="font-weight:700;color:var(--amber);min-width:58px;text-align:right">${altNaHCO3g.toFixed(2)} g</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 8px;white-space:nowrap"
            onclick="wcAddToRecipe('Bicarbonate de sodium (${suffix})',${altNaHCO3g.toFixed(2)},'g','${otherType}')">
            <i class="fas fa-plus"></i> ${t('rec.wc_add_recipe')}
          </button>
        </div>
      </div>`;
  }

  // ── Acid doses ──
  const activeAcids = Object.entries(acidDoses).filter(([, mL]) => mL >= 0.05);
  if (activeAcids.length) {
    html += `<div style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--danger);margin-bottom:6px"><i class="fas fa-vial"></i> ${t('rec.wc_acids')}</div>`;
    html += `<div style="display:flex;flex-direction:column;gap:5px">`;
    activeAcids.forEach(([acid, mL]) => {
      html += `
        <div style="display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:5px 10px">
          <span style="flex:1;font-size:.83rem">${acid}</span>
          <span style="font-weight:700;color:var(--amber);min-width:58px;text-align:right">${mL.toFixed(1)} mL</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 8px;white-space:nowrap"
            onclick="wcAddToRecipe('${acid} (${suffix})',${mL.toFixed(1)},'mL','${otherType}')">
            <i class="fas fa-plus"></i> ${t('rec.wc_add_recipe')}
          </button>
        </div>`;
    });
    html += `</div>`;
  }

  const div = document.getElementById(containerId);
  div.innerHTML = html;
  div.style.display = 'block';
}

function wcAddToRecipe(name, qty, unit, otherType = 'empatage') {
  // Update if already present, otherwise add new row
  const existing = recIngredients.find(i => i.name === name && i.category === 'autre');
  if (existing) {
    existing.quantity   = qty;
    existing.unit       = unit;
    existing.other_type = otherType;
    renderIngredientRows();
    toast(t('rec.wc_updated').replace('${name}', name), 'info');
    return;
  }
  recIngredients.push({
    _rid: ++ingRowId, category: 'autre', inventory_item_id: null,
    name, quantity: qty, unit,
    hop_type: null, other_type: otherType, other_time: null, notes: '',
  });
  renderIngredientRows();
  toast(t('rec.wc_added').replace('${name}', name), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// GITHUB EXPORT
// ══════════════════════════════════════════════════════════════════════════════

function renderSettingsGithub() {
  const gh = appSettings.github || {};
  const v  = gh.vitrine || {};
  const d  = gh.data    || {};
  const bk = gh.backup  || {};
  // Migration depuis l'ancien format à champs individuels
  const vitTargets = v.targets?.length ? v.targets
    : [{ provider: v.provider || 'github', apiUrl: v.apiUrl || '', repo: v.repo || '', branch: v.branch || 'main', pat: v.pat || '' }];
  const datTargets = d.targets?.length ? d.targets
    : [{ provider: d.provider || 'github', apiUrl: d.apiUrl || '', repo: d.repo || '', branch: d.branch || 'main', pat: d.pat || '' }];
  _renderGhTargets('vit', vitTargets);
  _renderGhTargets('dat', datTargets);
  // Sauvegarde automatique
  const enabled = !!bk.enabled;
  document.getElementById('gh-backup-enabled').checked = enabled;
  document.getElementById('gh-backup-freq').value    = bk.freq    || 'daily';
  document.getElementById('gh-backup-hour').value   = bk.hour    ?? 2;
  document.getElementById('gh-backup-min').value    = bk.minute  ?? 0;
  document.getElementById('gh-backup-weekday').value = bk.weekday ?? 0;
  document.getElementById('gh-backup-day').value    = bk.day     || 1;
  document.getElementById('gh-backup-notify').checked = !!bk.notify;
  document.getElementById('gh-backup-config').style.display = enabled ? 'flex' : 'none';
  ghBackupFreqChange();
  const lastEl = document.getElementById('gh-last-backup');
  lastEl.textContent = bk.lastBackup ? `${t('settings.github.last_backup')} : ${bk.lastBackup}` : '';
}

function ghBackupToggle() {
  const on = document.getElementById('gh-backup-enabled').checked;
  document.getElementById('gh-backup-config').style.display = on ? 'flex' : 'none';
}

function ghBackupFreqChange() {
  const freq = document.getElementById('gh-backup-freq').value;
  document.getElementById('gh-backup-dow-wrap').style.display = freq === 'weekly'  ? 'flex' : 'none';
  document.getElementById('gh-backup-dom-wrap').style.display = freq === 'monthly' ? 'flex' : 'none';
}

function _ghTargetHtml(section, idx, tgt = {}) {
  const isCustom = tgt.provider === 'custom';
  return `<div class="gh-target" style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <span style="font-size:.78rem;font-weight:700;color:var(--muted);text-transform:uppercase">${t('settings.github.dest_n').replace('${n}', idx + 1)}</span>
      <button class="btn btn-ghost btn-sm btn-icon" onclick="_ghRemoveTarget('${section}',${idx})" title="${t('common.delete')}"><i class="fas fa-trash-can" style="color:var(--danger)"></i></button>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px">
      <div class="field"><label>${t('settings.github.provider_label')}</label>
        <select class="gh-provider" onchange="this.closest('.gh-target').querySelector('.gh-url-wrap').style.display=this.value==='custom'?'':'none'">
          <option value="github"${tgt.provider !== 'custom' ? ' selected' : ''}>${t('settings.github.provider_github')}</option>
          <option value="custom"${tgt.provider === 'custom' ? ' selected' : ''}>${t('settings.github.provider_custom')}</option>
        </select>
      </div>
      <div class="gh-url-wrap field" style="${isCustom ? '' : 'display:none'}">
        <label>${t('settings.github.api_url_label')}</label>
        <input type="text" class="gh-url" placeholder="https://gitea.example.com/api/v1" value="${_vEsc(tgt.apiUrl || '')}">
      </div>
      <div class="field"><label>${t('settings.github.repo_label')} <span style="font-size:.78rem;color:var(--muted)">(owner/repo)</span></label>
        <input type="text" class="gh-repo" placeholder="ex: user/repo" value="${_vEsc(tgt.repo || '')}" onblur="const n=_normalizeGitRepo(this.value);if(n)this.value=n">
      </div>
      <div class="field"><label>${t('settings.github.vitrine_branch')}</label>
        <input type="text" class="gh-branch" placeholder="main" value="${_vEsc(tgt.branch || 'main')}">
      </div>
      <div class="field"><label>${t('settings.github.vitrine_pat')}</label>
        <div style="display:flex;gap:6px">
          <input type="password" class="gh-pat" placeholder="ghp_…" value="${_vEsc(tgt.pat || '')}" style="flex:1">
          <button class="btn btn-ghost btn-sm btn-icon" onclick="const i=this.previousElementSibling;i.type=i.type==='password'?'text':'password'" title="${t('settings.github.show_hide')}"><i class="fas fa-eye"></i></button>
        </div>
      </div>
    </div>
  </div>`;
}

function _renderGhTargets(section, targets) {
  const el = document.getElementById(`gh-${section}-targets`);
  if (!el) return;
  el.innerHTML = (targets.length ? targets : [{}]).map((tgt, i) => _ghTargetHtml(section, i, tgt)).join('');
}

function _captureGhTargets(section) {
  const el = document.getElementById(`gh-${section}-targets`);
  if (!el) return [];
  return [...el.querySelectorAll('.gh-target')].map(div => ({
    provider: div.querySelector('.gh-provider')?.value || 'github',
    apiUrl:   (div.querySelector('.gh-url')?.value || '').trim().replace(/\/+$/, ''),
    repo:     _normalizeGitRepo(div.querySelector('.gh-repo')?.value || ''),
    branch:   (div.querySelector('.gh-branch')?.value || '').trim() || 'main',
    pat:      (div.querySelector('.gh-pat')?.value || '').trim(),
  }));
}

function _ghAddTarget(section) {
  _captureGithubSettings();
  const key = section === 'vit' ? 'vitrine' : 'data';
  const targets = [...(appSettings.github?.[key]?.targets || [{}])];
  targets.push({ provider: 'github', apiUrl: '', repo: '', branch: 'main', pat: '' });
  _renderGhTargets(section, targets);
}

function _ghRemoveTarget(section, idx) {
  _captureGithubSettings();
  const key = section === 'vit' ? 'vitrine' : 'data';
  const targets = [...(appSettings.github?.[key]?.targets || [])];
  if (targets.length <= 1) return;
  targets.splice(idx, 1);
  appSettings.github[key].targets = targets;
  _renderGhTargets(section, targets);
}

// Extrait "owner/repo" depuis une URL Git complète ou un chemin avec .git
function _normalizeGitRepo(raw) {
  if (!raw) return '';
  raw = raw.trim();
  try {
    // Si c'est une URL complète (http://host/owner/repo.git)
    const url = new URL(raw);
    return url.pathname.replace(/^\/+/, '').replace(/\.git$/, '');
  } catch(_) {}
  // Sinon juste enlever le .git éventuel
  return raw.replace(/\.git$/, '');
}

function _captureGithubSettings() {
  appSettings.github = {
    vitrine: { targets: _captureGhTargets('vit') },
    data:    { targets: _captureGhTargets('dat') },
    backup: {
      enabled: document.getElementById('gh-backup-enabled').checked,
      freq:    document.getElementById('gh-backup-freq').value,
      hour:    parseInt(document.getElementById('gh-backup-hour').value) || 2,
      minute:  parseInt(document.getElementById('gh-backup-min').value)  || 0,
      weekday: parseInt(document.getElementById('gh-backup-weekday').value) ?? 0,
      day:     parseInt(document.getElementById('gh-backup-day').value)  || 1,
      lastBackup: appSettings.github?.backup?.lastBackup || null,
      notify:  document.getElementById('gh-backup-notify').checked,
    },
  };
  saveSettings();
}

function saveGithubSettings() {
  _captureGithubSettings();
  toast(t('settings.toast.github_saved'), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// SETTINGS — IA IMAGE
// ══════════════════════════════════════════════════════════════════════════════

function renderAIModelList() {
  const prov     = document.getElementById('ai-provider').value;
  const selMod   = document.getElementById('ai-model');
  const sizeWrap = document.getElementById('ai-size-wrap');
  if (prov === 'openai') {
    selMod.innerHTML = `
      <option value="gpt-image-1.5">gpt-image-1.5 (recommandé)</option>
      <option value="chatgpt-image-latest">chatgpt-image-latest</option>
      <option value="gpt-image-1">gpt-image-1</option>
      <option value="gpt-image-1-mini">gpt-image-1-mini (économique)</option>`;
    sizeWrap.style.display = '';
    document.getElementById('ai-quality-wrap').style.display = '';
  } else {
    selMod.innerHTML = `
      <option value="gemini-3.1-flash-image-preview">Gemini 3.1 Flash Image (recommandé)</option>
      <option value="gemini-2.5-flash-image">Gemini 2.5 Flash Image (stable)</option>
      <option value="gemini-3-pro-image-preview">Gemini 3 Pro Image</option>`;
    sizeWrap.style.display = 'none';
    document.getElementById('ai-quality-wrap').style.display = 'none';
  }
}

function renderAITextModelList() {
  const prov = document.getElementById('ai-text-provider').value;
  const sel  = document.getElementById('ai-text-model');
  if (prov === 'openai') {
    sel.innerHTML = `
      <option value="gpt-4.1">gpt-4.1 (recommandé)</option>
      <option value="gpt-4.1-mini">gpt-4.1-mini (rapide)</option>
      <option value="gpt-4.1-nano">gpt-4.1-nano (économique)</option>
      <option value="gpt-4o">gpt-4o</option>
      <option value="gpt-4o-mini">gpt-4o-mini</option>
      <option value="o4-mini">o4-mini (raisonnement)</option>
      <option value="o3-mini">o3-mini (raisonnement)</option>
      <option value="gpt-5">gpt-5 (frontier)</option>
      <option value="gpt-5-mini">gpt-5-mini (frontier)</option>
      <option value="gpt-3.5-turbo">gpt-3.5-turbo (legacy)</option>`;
  } else {
    sel.innerHTML = `
      <option value="gemini-2.5-flash">gemini-2.5-flash (recommandé)</option>
      <option value="gemini-2.5-flash-lite">gemini-2.5-flash-lite (rapide)</option>
      <option value="gemini-2.5-pro">gemini-2.5-pro (haute qualité)</option>
      <option value="gemini-3-flash-preview">gemini-3-flash-preview</option>
      <option value="gemini-3.1-flash-lite-preview">gemini-3.1-flash-lite-preview</option>
      <option value="gemini-3.1-pro-preview">gemini-3.1-pro-preview</option>`;
  }
}

function renderSettingsAI() {
  const ai = appSettings.ai || {};
  // Migration: ancienne clé unique → clé Gemini
  const geminiKey = ai.geminiApiKey || (ai.provider !== 'openai' ? ai.apiKey : '') || '';
  const openaiKey = ai.openaiApiKey || (ai.provider === 'openai' ? ai.apiKey : '') || '';
  document.getElementById('ai-gemini-key').value = geminiKey;
  document.getElementById('ai-openai-key').value = openaiKey;
  document.getElementById('ai-provider').value   = ai.provider || 'openai';
  renderAIModelList();
  if (ai.model)   document.getElementById('ai-model').value   = ai.model;
  if (ai.size)    document.getElementById('ai-size').value    = ai.size;
  if (ai.quality) document.getElementById('ai-quality').value = ai.quality;
  document.getElementById('ai-text-provider').value = ai.textProvider || 'gemini';
  renderAITextModelList();
  if (ai.textModel) document.getElementById('ai-text-model').value = ai.textModel;
}

function saveAISettings() {
  appSettings.ai = {
    provider:     document.getElementById('ai-provider').value,
    model:        document.getElementById('ai-model').value,
    geminiApiKey: document.getElementById('ai-gemini-key').value.trim(),
    openaiApiKey: document.getElementById('ai-openai-key').value.trim(),
    textProvider: document.getElementById('ai-text-provider').value,
    textModel:    document.getElementById('ai-text-model').value,
    size:         document.getElementById('ai-size').value,
    quality:      document.getElementById('ai-quality').value,
  };
  saveSettings();
  toast(t('settings.toast.ai_saved'), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// TELEGRAM NOTIFICATIONS
// ══════════════════════════════════════════════════════════════════════════════

function renderSettingsNotif() {
  const tg = appSettings.telegram || {};
  const n  = tg.notifs || {};
  document.getElementById('tg-token').value   = tg.token  || '';
  document.getElementById('tg-chat-id').value = tg.chatId || '';
  document.getElementById('tg-tz').value      = tg.tz     || 'Europe/Paris';
  // Brassins
  const b = n.brews || {};
  document.getElementById('tg-brews-enabled').checked = !!b.enabled;
  document.getElementById('tg-brews-hour').value = b.hour ?? 8;
  document.getElementById('tg-brews-min').value  = b.minute ?? 0;
  // Cave
  const c = n.cave || {};
  document.getElementById('tg-cave-enabled').checked = !!c.enabled;
  document.getElementById('tg-cave-day').value  = c.day    ?? 1;
  document.getElementById('tg-cave-hour').value = c.hour   ?? 8;
  document.getElementById('tg-cave-min').value  = c.minute ?? 0;
  // Inventaire
  const i = n.inventory || {};
  document.getElementById('tg-inv-enabled').checked = !!i.enabled;
  document.getElementById('tg-inv-day').value  = i.day    ?? 1;
  document.getElementById('tg-inv-hour').value = i.hour   ?? 8;
  document.getElementById('tg-inv-min').value  = i.minute ?? 0;
  // Fermentation reminders
  const fr = n.ferm_reminders || {};
  document.getElementById('tg-ferm-enabled').checked = !!fr.enabled;
  document.getElementById('tg-ferm-hour').value = fr.hour   ?? 8;
  document.getElementById('tg-ferm-min').value  = fr.minute ?? 0;
  // Bottling alert
  const bo = n.bottling || {};
  document.getElementById('tg-bottling-enabled').checked = bo.enabled ?? true;
  // Spindle gravity stability
  const ss = n.spindle_stable || {};
  document.getElementById('tg-spindle-enabled').checked = !!ss.enabled;
  document.getElementById('tg-spindle-config').style.display = ss.enabled ? 'flex' : 'none';
  document.getElementById('tg-spindle-days').value = ss.days ?? 3;
  // Événements brassicoles
  const ev = appSettings.brewEvents || {};
  const evEnabled = !!ev.enabled;
  document.getElementById('tg-events-enabled').checked = evEnabled;
  document.getElementById('tg-events-config').style.display = evEnabled ? 'flex' : 'none';
  document.getElementById('tg-events-remind').checked  = ev.remind    ?? true;
  document.getElementById('tg-events-day').checked     = ev.event_day ?? true;
  document.getElementById('tg-events-hour').value      = ev.hour      ?? 8;
  document.getElementById('tg-events-min').value       = ev.minute    ?? 0;
  document.getElementById('tg-test-result').textContent = '';
  const _rdLabel = document.querySelector('[data-i18n="settings.notif.remind_45"]');
  if (_rdLabel) _rdLabel.textContent = t('settings.notif.remind_45').replace('${days}', appSettings.defaultBrewReminderDays || 45);
}

function saveTelegramSettings() {
  const g = id => document.getElementById(id);
  appSettings.telegram = {
    token:  g('tg-token').value.trim(),
    chatId: g('tg-chat-id').value.trim(),
    tz:     g('tg-tz').value.trim() || 'Europe/Paris',
    notifs: {
      brews: {
        enabled: g('tg-brews-enabled').checked,
        hour:    parseInt(g('tg-brews-hour').value) || 0,
        minute:  parseInt(g('tg-brews-min').value)  || 0,
      },
      cave: {
        enabled: g('tg-cave-enabled').checked,
        day:     parseInt(g('tg-cave-day').value)   || 1,
        hour:    parseInt(g('tg-cave-hour').value)  || 0,
        minute:  parseInt(g('tg-cave-min').value)   || 0,
      },
      inventory: {
        enabled: g('tg-inv-enabled').checked,
        day:     parseInt(g('tg-inv-day').value)    || 1,
        hour:    parseInt(g('tg-inv-hour').value)   || 0,
        minute:  parseInt(g('tg-inv-min').value)    || 0,
      },
      ferm_reminders: {
        enabled: g('tg-ferm-enabled').checked,
        hour:    parseInt(g('tg-ferm-hour').value)  || 0,
        minute:  parseInt(g('tg-ferm-min').value)   || 0,
      },
      bottling: {
        enabled: g('tg-bottling-enabled').checked,
      },
      spindle_stable: {
        enabled: g('tg-spindle-enabled').checked,
        days:    parseInt(g('tg-spindle-days').value) || 3,
      },
    },
  };
  appSettings.brewEvents = {
    enabled:   g('tg-events-enabled').checked,
    remind:    g('tg-events-remind').checked,
    event_day: g('tg-events-day').checked,
    hour:      parseInt(g('tg-events-hour').value) || 8,
    minute:    parseInt(g('tg-events-min').value)  || 0,
  };
  saveSettings();
  toast(t('settings.toast.notif_saved'), 'success');
}

async function testTelegramConnection() {
  const token   = document.getElementById('tg-token').value.trim();
  const chat_id = document.getElementById('tg-chat-id').value.trim();
  const res = document.getElementById('tg-test-result');
  if (!token || !chat_id) { res.style.color='var(--danger)'; res.textContent=t('settings.notif.tg_required'); return; }
  res.style.color = 'var(--muted)'; res.textContent = t('settings.notif.tg_sending');
  try {
    const r = await api('POST', '/api/telegram/test', { token, chat_id });
    if (r.success) { res.style.color='var(--success)'; res.textContent=t('settings.notif.tg_sent'); }
    else           { res.style.color='var(--danger)';  res.textContent=r.error||t('common.error'); }
  } catch(e) { res.style.color='var(--danger)'; res.textContent=t('settings.notif.tg_err_connect'); }
}

async function triggerTelegram(type) {
  const labels = { brews: t('settings.notif.tg_trigger_brews'), cave: t('settings.notif.tg_trigger_cave'), inventory: t('settings.notif.tg_trigger_inv'), ferm_reminders: t('settings.notif.tg_trigger_ferm') };
  try {
    const r = await api('POST', `/api/telegram/trigger/${type}`);
    if (r.success) toast(t('settings.notif.tg_triggered').replace('${label}', labels[type]), 'success');
    else           toast(r.error || t('settings.github.telegram_err'), 'error');
  } catch(e) { toast(t('settings.github.telegram_err'), 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════════
// IA IMAGE GENERATION
// ══════════════════════════════════════════════════════════════════════════════

async function generateBeerImage() {
  // Recharger les paramètres depuis le serveur pour garantir que la clé API est à jour
  // (évite le cas où localStorage et DB sont désynchronisés après un rechargement de page)
  try {
    const fresh = await api('GET', '/api/app-settings');
    if (fresh && Object.keys(fresh).length) {
      _loadSettingsFromServer(fresh);
      // Mettre à jour la visibilité du bouton si la clé vient d'être chargée
      const aiConfigured = !!appSettings.ai?.apiKey;
      const genBtn = document.getElementById('beer-gen-ai-btn');
      const extraWrap = document.getElementById('beer-ai-extra-wrap');
      if (genBtn)    genBtn.style.display    = aiConfigured ? '' : 'none';
      if (extraWrap) extraWrap.style.display = aiConfigured ? '' : 'none';
    }
  } catch(e) { /* serveur inaccessible — on utilise le cache en mémoire */ }

  const ai = appSettings.ai || {};
  const imgApiKey = ai.provider === 'gemini'
    ? (ai.geminiApiKey || ai.apiKey || '')
    : (ai.openaiApiKey || ai.apiKey || '');
  if (!imgApiKey) {
    toast(t('settings.ai.key_required'), 'error');
    return;
  }
  const name  = document.getElementById('beer-f-name').value.trim() || 'craft beer';
  const type  = document.getElementById('beer-f-type').value.trim();
  const desc  = document.getElementById('beer-f-desc').value.trim();
  const extra = document.getElementById('beer-ai-extra').value.trim();

  const prompt = `A flat, rectangular craft beer label design for a beer named "${name}"` +
    (type  ? `, style: ${type}` : '') +
    (desc  ? `. ${desc}` : '') +
    (extra ? `. Additional instructions: ${extra}` : '') +
    '. The label fills the entire image. No bottle, no glass, no hands, no brewery logo, no made-up brand symbols, no ABV percentage, no bottle size, no volume indication. Decorative illustrated border, beer name prominently displayed, nature or ingredient-inspired background art. Flat lay, print-ready label artwork only.';

  const beerId   = document.getElementById('beer-f-id').value;
  const hadPhoto = !!document.getElementById('beer-f-photo-b64').value;

  const btn = document.getElementById('beer-gen-ai-btn');
  btn.disabled = true;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('settings.ai.generating')}`;
  try {
    let b64, mime = 'image/png';
    if (ai.provider === 'gemini') {
      const res = await _aiGenerateGemini(imgApiKey, ai.model || 'gemini-3.1-flash-image-preview', prompt);
      b64 = res.b64; mime = res.mime;
    } else {
      b64 = await _aiGenerateOpenAI(imgApiKey, ai.model || 'gpt-image-1', '1024x1536', ai.quality || 'auto', prompt);
    }
    const dataUrl = `data:${mime};base64,${b64}`;
    document.getElementById('beer-f-photo-b64').value = dataUrl;
    const prev = document.getElementById('beer-f-photo-preview');
    prev.src = dataUrl;
    prev.style.display = 'block';
    document.getElementById('beer-f-photo-remove').style.display = 'flex';
    // Auto-save si la bière existe déjà et n'avait pas de photo
    if (beerId && !hadPhoto) {
      const beerObj = S.beers.find(b => b.id === parseInt(beerId));
      if (beerObj) {
        const updated = await api('PUT', `/api/beers/${beerId}`, { ...beerObj, photo: dataUrl }).catch(() => null);
        if (updated) {
          const idx = S.beers.findIndex(b => b.id === parseInt(beerId));
          if (idx !== -1) S.beers[idx] = updated;
          toast(t('settings.ai.img_generated_auto'), 'success');
        } else {
          toast(t('settings.ai.img_generated_save'), 'success');
        }
      } else {
        toast(t('settings.ai.img_generated'), 'success');
      }
    } else {
      toast(t('settings.ai.img_generated'), 'success');
    }
  } catch(e) {
    const msg = e.message || String(e);
    let friendly = t('settings.ai.img_err') + ' ' + msg;
    if (msg.includes('quota') || msg.includes('RESOURCE_EXHAUSTED') || msg.includes('limit: 0')) {
      friendly = t('settings.ai.img_err_quota');
    } else if (msg.includes('API_KEY') || msg.includes('API key') || msg.includes('401') || msg.includes('403')) {
      friendly = t('settings.ai.img_err_key');
    } else if (msg.includes('model') && msg.includes('not found')) {
      friendly = t('settings.ai.img_err_model');
    } else if (msg.length > 120) {
      friendly = t('settings.ai.img_err') + ' ' + msg.slice(0, 120) + '…';
    }
    toast(friendly, 'error');
  }
  btn.disabled = false;
  btn.innerHTML = `<i class="fas fa-wand-magic-sparkles"></i> ${t('settings.ai.generate_btn')}`;
}

async function _aiGenerateOpenAI(apiKey, model, size, quality, prompt) {
  const body = { model, prompt, n: 1, size, quality };
  // gpt-image-1 returns b64_json by default; older models need it explicit
  if (model !== 'gpt-image-1') body.response_format = 'b64_json';
  const r = await fetch('https://api.openai.com/v1/images/generations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err?.error?.message || r.statusText);
  }
  const data = await r.json();
  return data.data[0].b64_json;
}

async function _aiGenerateGemini(apiKey, model, prompt) {
  // Imagen 4 models use the /predict endpoint
  if (model.startsWith('imagen-')) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:predict?key=${apiKey}`;
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instances: [{ prompt }], parameters: { sampleCount: 1 } }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err?.error?.message || r.statusText);
    }
    const data = await r.json();
    return { b64: data.predictions[0].bytesBase64Encoded, mime: data.predictions[0].mimeType || 'image/png' };
  }
  // Gemini native image models use generateContent
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { responseModalities: ['IMAGE', 'TEXT'], imageConfig: { aspectRatio: '3:4' } },
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err?.error?.message || r.statusText);
  }
  const data = await r.json();
  const parts = data.candidates?.[0]?.content?.parts || [];
  const imgPart = parts.find(p => p.inlineData?.data);
  if (!imgPart) throw new Error('Aucune image dans la réponse Gemini');
  return { b64: imgPart.inlineData.data, mime: imgPart.inlineData.mimeType || 'image/png' };
}

function renderSettingsLang() {
  const panel = document.getElementById('stab-lang');
  if (!panel) return;
  const codes = Object.keys(LOCALES);
  panel.innerHTML = `
    <div style="margin-bottom:22px">
      <div style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--info);margin-bottom:12px">
        <i class="fas fa-globe"></i> ${t('lang.current', 'Langue active')}
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${codes.map(code => {
          const meta = LOCALES[code]._meta || {};
          const active = code === _lang;
          return `<button class="btn ${active ? 'btn-primary' : 'btn-ghost'}" onclick="switchLang('${code}')">
            ${meta.flag || ''} ${meta.name || code}${active ? ' ✓' : ''}
          </button>`;
        }).join('')}
      </div>
    </div>
    <div style="padding-top:18px;border-top:1px solid var(--border)">
      <div style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--info);margin-bottom:8px">
        <i class="fas fa-language"></i> ${t('lang.contribute', 'Contribuer une traduction')}
      </div>
      <p style="font-size:.83rem;color:var(--muted);margin-bottom:14px">${t('lang.import_hint', 'Importez un fichier JSON pour ajouter une langue.')}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-ghost btn-sm" onclick="exportLocaleTemplate()">
          <i class="fas fa-file-export"></i> ${t('lang.export_template', 'Exporter le modèle (JSON)')}
        </button>
        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('import-locale-file').click()">
          <i class="fas fa-file-import"></i> ${t('lang.import_translation', 'Importer une traduction (JSON)')}
        </button>
        <input type="file" id="import-locale-file" accept=".json" style="display:none" onchange="importLocaleFile(this)">
      </div>
    </div>`;
}

function switchLang(code) {
  if (!LOCALES[code]) return;
  _lang   = code;
  _locale = LOCALES[code];
  localStorage.setItem('brewLang', code);
  api('PUT', '/api/app-settings', { lang: code }).catch(e => console.warn('[BrewHome] lang save failed:', e));
  applyI18n();
  renderSettingsLang();
  // Re-render current page so dynamic strings (catLabel etc.) update
  const activePage = document.querySelector('.page.active');
  if (activePage) _refreshPage(activePage.id.replace('page-', ''));
}

function exportLocaleTemplate() {
  const template = JSON.parse(JSON.stringify(LOCALES.fr));
  template._meta = { name: 'Your Language', flag: '🌐', code: 'xx' };
  const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'brewhome-locale-template.json'; a.click();
  URL.revokeObjectURL(url);
}

async function importLocaleFile(input) {
  const file = input.files[0];
  if (!file) return;
  try {
    const text   = await file.text();
    const locale = JSON.parse(text);
    const code   = locale._meta?.code || file.name.replace(/\.json$/, '');
    LOCALES[code] = locale;
    toast(t('lang.loaded').replace('${name}', locale._meta?.name || code), 'success');
    renderSettingsLang();
  } catch(e) {
    toast(t('lang.err_read'), 'error');
  }
  input.value = '';
}

