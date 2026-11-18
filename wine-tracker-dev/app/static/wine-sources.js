/* WeinSommelier - grapeminds search, combined search and source badges.
 *
 * Loaded by _wine_edit_modal.html after wine-modal.js. Relies on globals and
 * functions defined in that template: INGRESS, T, AI_ENABLED,
 * GRAPEMINDS_ENABLED, _reloadMode, showFormStep, populateFormFromAi,
 * populateFormMerge, downloadVivinoImage, setReloadLoading, showReloadToast.
 *
 * grapeminds has a monthly request quota, so searches only run on Enter or
 * the search button - never on every keystroke.
 */

// Form field -> element id, used for source badges.
var SOURCE_FIELD_IDS = {
  name: 'wine_name', producer: 'wine_producer', vintage: 'wine_year',
  wine_type: 'wine_type', region: 'wine_region', grape: 'wine_grape',
  price: 'wine_price', drink_from: 'wine_drink_from', drink_until: 'wine_drink_until',
  notes: 'wine_notes', alcohol_pct: 'wine_alcohol_pct', bottle_format: 'wine_bottle_format'
};

function _esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _tr(key, fallback) { return (T && T[key]) || fallback; }

function _setStatus(id, text, isError) {
  var el = document.getElementById(id);
  if (!el) return;
  if (!text) { el.style.display = 'none'; el.textContent = ''; return; }
  el.innerHTML = isError ? _esc(text) : '<div class="ai-spinner"></div>' + _esc(text);
  el.className = 'vivino-status' + (isError ? ' error' : '');
  el.style.display = '';
}

function _gmErrorText(code) {
  var map = {
    invalid_key: _tr('grapeminds_err_key', 'grapeminds: API key invalid'),
    rate_limited: _tr('grapeminds_err_quota', 'grapeminds: request limit reached'),
    no_api_key: _tr('grapeminds_err_key', 'grapeminds: no API key'),
    query_too_short: _tr('grapeminds_err_short', 'Please enter at least 3 characters')
  };
  return map[code] || _tr('grapeminds_error', 'grapeminds search failed');
}

function _getJson(url, opts) {
  opts = opts || {};
  opts.headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});
  return fetch(url, opts).then(function(r) {
    return r.json().catch(function() { return { ok: false, error: 'parse_error' }; });
  });
}

// ── Panels ───────────────────────────────────────────────────────────────────

function hideSourcePanels() {
  ['grapemindsStep', 'combinedStep'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

function _showOnlyPanel(id) {
  ['sourceStep', 'aiStep', 'vivinoStep', 'formStep'].forEach(function(pid) {
    var el = document.getElementById(pid);
    if (el) el.style.display = 'none';
  });
  hideSourcePanels();
  var panel = document.getElementById(id);
  if (panel) panel.style.display = '';
  var submitBtn = document.getElementById('wineSubmitBtn');
  if (submitBtn) submitBtn.style.display = 'none';
}

function onSourceGrapeminds() {
  _showOnlyPanel('grapemindsStep');
  var input = document.getElementById('gmSearchInput');
  if (input) { input.value = ''; input.focus(); }
  document.getElementById('gmResults').innerHTML = '';
  _setStatus('gmStatus', '');
}

function onSourceCombined() {
  _showOnlyPanel('combinedStep');
  _comb = { ai: null, aiImage: null, gm: [], vivino: [], gmPick: null, vivinoPick: null };
  var input = document.getElementById('combSearchInput');
  if (input) { input.value = ''; input.focus(); }
  var label = document.getElementById('combPhotoLabel');
  if (label) label.textContent = _tr('combined_photo', 'Photograph the label (optional)');
  var photoInput = document.querySelector('#combPhotoArea input[type=file]');
  var photoArea = document.getElementById('combPhotoArea');
  if (photoArea) photoArea.style.display = '';
  if (photoInput) photoInput.value = '';
  document.getElementById('combLists').style.display = 'none';
  _setStatus('combStatus', '');
}

// ── Source badges ────────────────────────────────────────────────────────────

function clearSourceBadges() {
  document.querySelectorAll('#wineForm .src-badge').forEach(function(b) { b.remove(); });
}

function markSources(sources) {
  clearSourceBadges();
  if (!sources) return;
  var labels = {
    grapeminds: 'grapeminds', vivino: 'Vivino',
    label: _tr('src_label', 'Etikett'), ai: _tr('src_ai', 'KI')
  };
  var titles = {
    grapeminds: _tr('src_grapeminds_title', 'Verified data from grapeminds'),
    vivino: _tr('src_vivino_title', 'From Vivino'),
    label: _tr('src_label_title', 'Read from the label by AI'),
    ai: _tr('src_ai_title', 'Estimated by AI - please check')
  };
  Object.keys(sources).forEach(function(field) {
    var id = SOURCE_FIELD_IDS[field];
    var src = sources[field];
    if (!id || !labels[src]) return;
    var input = document.getElementById(id);
    var label = input && input.parentElement ? input.parentElement.querySelector('label') : null;
    if (!label) return;
    var badge = document.createElement('span');
    badge.className = 'src-badge src-' + src;
    badge.textContent = labels[src];
    badge.title = titles[src];
    label.appendChild(badge);
  });
}

var _drinkOffset = null;

function _applyDrinkOffset() {
  if (!_drinkOffset) return false;
  var year = parseInt(document.getElementById('wine_year').value, 10);
  if (!year || year < 1900) return false;
  var fromEl = document.getElementById('wine_drink_from');
  var untilEl = document.getElementById('wine_drink_until');
  var changed = false;
  if (_drinkOffset[0] != null && !fromEl.value) { fromEl.value = year + Number(_drinkOffset[0]); changed = true; }
  if (_drinkOffset[1] != null && !untilEl.value) { untilEl.value = year + Number(_drinkOffset[1]); changed = true; }
  if (changed) markSources(Object.assign({}, _lastSources, { drink_from: 'grapeminds', drink_until: 'grapeminds' }));
  return changed;
}

var _lastSources = {};

document.addEventListener('change', function(e) {
  if (e.target && e.target.id === 'wine_year') _applyDrinkOffset();
});

function _applyFields(fields, sources, imageFilename) {
  _drinkOffset = fields.drink_offset || null;
  _lastSources = sources || {};
  populateFormFromAi(fields, imageFilename || null);
  _applyDrinkOffset();
  if (fields.rating) {
    var starVal = Math.round(Number(fields.rating));
    if (starVal >= 1 && starVal <= 5) {
      var starEl = document.getElementById('wine_star' + starVal);
      if (starEl) starEl.checked = true;
    }
  }
  markSources(sources);
}

// ── grapeminds only ──────────────────────────────────────────────────────────

var _gmResults = [];

function _renderGmList(containerId, items, onClickFn, selectedIdx) {
  var container = document.getElementById(containerId);
  container.innerHTML = items.map(function(item, idx) {
    var meta = [];
    if (item.producer) meta.push(_esc(item.producer));
    if (item.year) meta.push(item.year);
    if (item.wine_type) meta.push(_esc(T['wine_type_' + item.wine_type] || item.wine_type));
    return '<div class="vivino-result-item src-result' + (idx === selectedIdx ? ' selected' : '') +
      '" tabindex="0" role="button" onclick="' + onClickFn + '(' + idx + ')">' +
      '<div class="src-result-icon"><i class="mdi mdi-glass-wine"></i></div>' +
      '<div class="vivino-result-info">' +
        '<div class="vivino-result-name">' + _esc(item.name) + '</div>' +
        '<div class="vivino-result-meta">' + meta.join(' · ') + '</div>' +
      '</div></div>';
  }).join('');
}

function grapemindsSearch() {
  var q = (document.getElementById('gmSearchInput').value || '').trim();
  if (q.length < 3) { _setStatus('gmStatus', _gmErrorText('query_too_short'), true); return; }
  _setStatus('gmStatus', _tr('grapeminds_searching', 'Searching grapeminds…'));
  document.getElementById('gmResults').innerHTML = '';
  _getJson(INGRESS + '/api/grapeminds-search?q=' + encodeURIComponent(q))
    .then(function(data) {
      if (!data.ok) { _gmResults = []; _setStatus('gmStatus', _gmErrorText(data.error), true); return; }
      _gmResults = data.results || [];
      if (!_gmResults.length) { _setStatus('gmStatus', _tr('vivino_no_results', 'No results'), true); return; }
      _setStatus('gmStatus', '');
      _renderGmList('gmResults', _gmResults, 'selectGrapemindsResult', -1);
    })
    .catch(function() { _setStatus('gmStatus', _gmErrorText(), true); });
}

function selectGrapemindsResult(idx) {
  var item = _gmResults[idx];
  if (!item) return;
  _setStatus('gmStatus', _tr('grapeminds_loading', 'Loading details…'));
  document.getElementById('gmResults').innerHTML = '';
  _getJson(INGRESS + '/api/grapeminds-wine/' + encodeURIComponent(item.grapeminds_id))
    .then(function(data) {
      if (!data.ok) { _setStatus('gmStatus', _gmErrorText(data.error), true); return; }
      _setStatus('gmStatus', '');
      _applyFields(data.fields, data.sources, null);
    })
    .catch(function() { _setStatus('gmStatus', _gmErrorText(), true); });
}

function reloadViaGrapeminds() {
  var producer = document.getElementById('wine_producer').value.trim();
  var name = document.getElementById('wine_name').value.trim();
  var q = (producer && name.indexOf(producer) === -1 ? producer + ' ' : '') + name;
  if (q.length < 3) { showReloadToast(_gmErrorText('query_too_short'), false); return; }
  setReloadLoading(true);
  _getJson(INGRESS + '/api/grapeminds-search?q=' + encodeURIComponent(q))
    .then(function(data) {
      if (!data.ok || !data.results || !data.results.length) {
        throw new Error(data.ok ? 'none' : data.error);
      }
      return _getJson(INGRESS + '/api/grapeminds-wine/' + data.results[0].grapeminds_id);
    })
    .then(function(data) {
      setReloadLoading(false);
      if (!data.ok) { showReloadToast(_gmErrorText(data.error), false); return; }
      populateFormMerge(data.fields, null);
    })
    .catch(function(err) {
      setReloadLoading(false);
      showReloadToast(err && err.message === 'none'
        ? _tr('vivino_no_results', 'No results') : _gmErrorText(err && err.message), false);
    });
}

// ── Combined search ──────────────────────────────────────────────────────────

var _comb = { ai: null, aiImage: null, gm: [], vivino: [], gmPick: null, vivinoPick: null };

function combinedPhoto(file) {
  if (!file || !AI_ENABLED) return;
  var label = document.getElementById('combPhotoLabel');
  if (label) label.textContent = _tr('ai_analyzing', 'Analyzing…');
  _setStatus('combStatus', _tr('ai_analyzing', 'Analyzing…'));
  var fd = new FormData();
  fd.append('image', file);
  _getJson(INGRESS + '/api/analyze-wine', { method: 'POST', body: fd })
    .then(function(data) {
      if (data.image_filename) _comb.aiImage = data.image_filename;
      if (!data.ok) {
        _setStatus('combStatus', _tr('ai_error', 'AI analysis failed'), true);
        if (label) label.textContent = _tr('combined_photo', 'Photograph the label (optional)');
        return;
      }
      _comb.ai = data.fields || {};
      if (label) label.textContent = _tr('combined_photo_done', 'Label read ✓');
      var f = _comb.ai;
      var q = [f.producer, f.name].filter(Boolean).join(' ').trim();
      if (f.producer && f.name && f.name.indexOf(f.producer) !== -1) q = f.name;
      document.getElementById('combSearchInput').value = q;
      if (q.length >= 3) combinedSearch(); else _setStatus('combStatus', '');
    })
    .catch(function() {
      _setStatus('combStatus', _tr('ai_error', 'AI analysis failed'), true);
      if (label) label.textContent = _tr('combined_photo', 'Photograph the label (optional)');
    });
}

function combinedSearch() {
  var q = (document.getElementById('combSearchInput').value || '').trim();
  if (q.length < 3) { _setStatus('combStatus', _gmErrorText('query_too_short'), true); return; }
  var year = _comb.ai && _comb.ai.vintage ? String(_comb.ai.vintage) : '';
  var vivinoQ = year && q.indexOf(year) === -1 ? q + ' ' + year : q;
  _setStatus('combStatus', _tr('combined_searching', 'Searching grapeminds and Vivino…'));
  document.getElementById('combLists').style.display = 'none';
  _comb.gmPick = null; _comb.vivinoPick = null;

  var gmReq = _getJson(INGRESS + '/api/grapeminds-search?q=' + encodeURIComponent(q))
    .catch(function() { return { ok: false, error: 'network_error' }; });
  var vivReq = _getJson(INGRESS + '/api/vivino-search?q=' + encodeURIComponent(vivinoQ))
    .catch(function() { return { ok: false, error: 'network_error' }; });

  Promise.all([gmReq, vivReq]).then(function(res) {
    var gm = res[0], viv = res[1];
    _comb.gm = gm.ok ? (gm.results || []) : [];
    _comb.vivino = viv.ok ? (viv.results || []).slice(0, 8) : [];
    // Preselect the top hit of each list - the user can change or deselect.
    if (_comb.gm.length) _comb.gmPick = 0;
    if (_comb.vivino.length) _comb.vivinoPick = 0;
    _renderCombined(gm.ok ? null : _gmErrorText(gm.error),
                    viv.ok ? null : _tr('vivino_error', 'Vivino search failed'));
    _setStatus('combStatus', '');
    document.getElementById('combLists').style.display = '';
  });
}

function _noneRow(fn, selected, text) {
  return '<div class="vivino-result-item src-result src-none' + (selected ? ' selected' : '') +
    '" tabindex="0" role="button" onclick="' + fn + '(-1)">' +
    '<div class="src-result-icon"><i class="mdi mdi-close-circle-outline"></i></div>' +
    '<div class="vivino-result-info"><div class="vivino-result-meta">' + _esc(text) + '</div></div></div>';
}

function _renderCombined(gmError, vivError) {
  var gmBox = document.getElementById('combGmResults');
  if (gmError) {
    gmBox.innerHTML = '<div class="vivino-status error">' + _esc(gmError) + '</div>';
  } else {
    _renderGmList('combGmResults', _comb.gm, 'combPickGm', _comb.gmPick);
    gmBox.innerHTML += _noneRow('combPickGm', _comb.gmPick === null,
      _tr('combined_none_gm', 'None of these / skip grapeminds'));
  }

  var vivBox = document.getElementById('combVivinoResults');
  if (vivError) {
    vivBox.innerHTML = '<div class="vivino-status error">' + _esc(vivError) + '</div>';
  } else {
    vivBox.innerHTML = _comb.vivino.map(function(item, idx) {
      var meta = [];
      if (item.year) meta.push(item.year);
      if (item.region) meta.push(_esc(item.region));
      if (item.price) meta.push(_esc(item.price));
      var img = item.image_url
        ? '<img class="src-result-img" src="' + _esc(item.image_url) + '" alt="" loading="lazy">'
        : '<div class="src-result-icon"><i class="mdi mdi-glass-wine"></i></div>';
      return '<div class="vivino-result-item src-result' + (idx === _comb.vivinoPick ? ' selected' : '') +
        '" tabindex="0" role="button" onclick="combPickVivino(' + idx + ')">' + img +
        '<div class="vivino-result-info">' +
          '<div class="vivino-result-name">' + _esc(item.name) + '</div>' +
          '<div class="vivino-result-meta">' + meta.join(' · ') + '</div>' +
          (item.rating ? '<span class="vivino-result-rating"><i class="mdi mdi-star"></i> ' +
            Number(item.rating).toFixed(1) + '</span>' : '') +
        '</div></div>';
    }).join('') + _noneRow('combPickVivino', _comb.vivinoPick === null,
      _tr('combined_none_vivino', 'None of these / skip Vivino'));
  }
}

function combPickGm(idx) { _comb.gmPick = idx >= 0 ? idx : null; _renderCombined(); }
function combPickVivino(idx) { _comb.vivinoPick = idx >= 0 ? idx : null; _renderCombined(); }

function combinedApply() {
  var gmItem = _comb.gmPick !== null ? _comb.gm[_comb.gmPick] : null;
  var vivItem = _comb.vivinoPick !== null ? _comb.vivino[_comb.vivinoPick] : null;
  var btn = document.getElementById('combApplyBtn');
  if (btn) btn.disabled = true;
  _setStatus('combStatus', _tr('grapeminds_loading', 'Loading details…'));

  _getJson(INGRESS + '/api/combine', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ai: _comb.ai || {},
      grapeminds_id: gmItem ? gmItem.grapeminds_id : null,
      vivino: vivItem
    })
  })
  .then(function(data) {
    if (btn) btn.disabled = false;
    if (!data.ok) { _setStatus('combStatus', _tr('combined_error', 'Merging failed'), true); return; }
    _setStatus('combStatus', '');
    document.getElementById('wine_vivino_id').value = vivItem && vivItem.vivino_id ? vivItem.vivino_id : '';
    _applyFields(data.fields, data.sources, _comb.aiImage);
    // Bottle shot from Vivino only when there is no label photo
    if (!_comb.aiImage && vivItem && vivItem.image_url) downloadVivinoImage(vivItem.image_url);
    if (data.warnings && data.warnings.length) {
      var w = data.warnings[0].replace('grapeminds_', '');
      showReloadToast(_gmErrorText(w), false);
    }
  })
  .catch(function() {
    if (btn) btn.disabled = false;
    _setStatus('combStatus', _tr('combined_error', 'Merging failed'), true);
  });
}

// ── In-app camera ────────────────────────────────────────────────────────────
// Some phone apps (notably the Home Assistant companion app) only offer the
// gallery for <input type=file capture>. When the page runs in a secure
// context we open the camera ourselves via getUserMedia; otherwise we fall
// back to a capture file input.

var _cam = { stream: null, onFile: null };

function _cameraSupported() {
  return !!(window.isSecureContext && navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia);
}

function _fallbackCaptureInput(onFile) {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*';
  input.setAttribute('capture', 'environment');
  input.style.display = 'none';
  input.onchange = function() {
    if (input.files && input.files[0]) onFile(input.files[0]);
    input.remove();
  };
  document.body.appendChild(input);
  input.click();
}

function _cameraOverlay() {
  var ov = document.getElementById('camOverlay');
  if (ov) return ov;
  ov = document.createElement('div');
  ov.id = 'camOverlay';
  ov.className = 'cam-overlay';
  ov.innerHTML =
    '<video id="camVideo" autoplay playsinline muted></video>' +
    '<div class="cam-hint" id="camHint"></div>' +
    '<div class="cam-controls">' +
      '<button type="button" class="cam-btn" onclick="closeCameraCapture()" aria-label="' +
        _esc(_tr('photo_cancel', 'Cancel')) + '"><i class="mdi mdi-close"></i></button>' +
      '<button type="button" class="cam-shutter" onclick="takeCameraPhoto()" aria-label="' +
        _esc(_tr('photo_take', 'Take photo')) + '"></button>' +
      '<label class="cam-btn" aria-label="' + _esc(_tr('photo_gallery', 'Gallery')) + '">' +
        '<i class="mdi mdi-image-multiple"></i>' +
        '<input type="file" accept="image/*" onchange="cameraPickedFile(this)"></label>' +
    '</div>';
  document.body.appendChild(ov);
  return ov;
}

function openCameraCapture(onFile) {
  if (!_cameraSupported()) { _fallbackCaptureInput(onFile); return; }
  _cam.onFile = onFile;
  var ov = _cameraOverlay();
  var hint = document.getElementById('camHint');
  hint.textContent = _tr('photo_starting', 'Starting camera\u2026');
  ov.style.display = 'flex';
  navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } }
  }).then(function(stream) {
    _cam.stream = stream;
    var video = document.getElementById('camVideo');
    video.srcObject = stream;
    hint.textContent = _tr('photo_hint', 'Fit the label into the frame');
  }).catch(function() {
    // Permission denied or no camera: close and use the system picker.
    closeCameraCapture();
    _fallbackCaptureInput(onFile);
  });
}

function closeCameraCapture() {
  if (_cam.stream) { _cam.stream.getTracks().forEach(function(t) { t.stop(); }); }
  _cam.stream = null;
  var video = document.getElementById('camVideo');
  if (video) video.srcObject = null;
  var ov = document.getElementById('camOverlay');
  if (ov) ov.style.display = 'none';
}

function takeCameraPhoto() {
  var video = document.getElementById('camVideo');
  if (!video || !video.videoWidth) return;
  var canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  var onFile = _cam.onFile;
  canvas.toBlob(function(blob) {
    closeCameraCapture();
    if (!blob || !onFile) return;
    var file = new File([blob], 'etikett-' + Date.now() + '.jpg', { type: 'image/jpeg' });
    onFile(file);
  }, 'image/jpeg', 0.9);
}

function cameraPickedFile(input) {
  var file = input.files && input.files[0];
  var onFile = _cam.onFile;
  input.value = '';
  closeCameraCapture();
  if (file && onFile) onFile(file);
}

document.addEventListener('keydown', function(e) {
  var ov = document.getElementById('camOverlay');
  if (e.key === 'Escape' && ov && ov.style.display !== 'none') closeCameraCapture();
});
