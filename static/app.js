(function () {
    function ensureToastContainer() {
        let container = document.getElementById('toastContainer');
        if (container) return container;

        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
        return container;
    }

    // Global helpers for numeric-only and BP auto-formatting (fallback script)
    document.addEventListener('DOMContentLoaded', () => {
        try {
            const unitSuffixMap = {
                cm: ' cm',
                kg: ' kg',
                F: ' F',
                '%': ' %',
                bpm: ' bpm',
                'mg/dL': ' mg/dL'
            };

            const stripUnit = (value) => String(value ?? '').replace(/\s*(cm|kg|F|%|bpm|mg\/dL)\s*$/i, '').trim();
            const cleanNumeric = (value) => stripUnit(value).replace(/[^0-9.]/g, '');

            window.stripUnitValue = window.stripUnitValue || stripUnit;
            window.cleanNumericValue = window.cleanNumericValue || cleanNumeric;

            document.querySelectorAll('.numeric-only').forEach(el => {
                el.addEventListener('input', () => { el.value = cleanNumeric(el.value); });
            });
            document.querySelectorAll('.bp-input').forEach(bp => {
                bp.addEventListener('blur', () => {
                    let v = (bp.value || '').toString();
                    if (v.includes('/')) return;
                    const digits = v.replace(/[^0-9]/g, '');
                    if (digits.length >= 4) {
                        const first = digits.slice(0,3);
                        const second = digits.slice(3);
                        bp.value = `${first}/${second}`;
                    }
                });
                bp.addEventListener('keydown', (e) => {
                    const allowed = ['Backspace','Tab','ArrowLeft','ArrowRight','Delete'];
                    if (allowed.includes(e.key)) return;
                    if (/^[0-9]$/.test(e.key) || e.key === '/') return;
                    e.preventDefault();
                });
            });

            const formatUnitField = (el) => {
                if (!el) return;
                const unit = el.dataset.unit || '';
                const numeric = cleanNumeric(el.value);
                if (!numeric) return;
                el.value = unit ? `${numeric}${unitSuffixMap[unit] || ` ${unit}`}` : numeric;
            };

            const focusUnitField = (el) => {
                if (!el) return;
                el.value = cleanNumeric(el.value);
            };

            document.querySelectorAll('.unit-field').forEach(el => {
                el.addEventListener('focus', () => focusUnitField(el));
                el.addEventListener('blur', () => formatUnitField(el));
            });
        } catch (e) {
            console.error('Numeric/BP global wiring failed', e);
        }
    });

    window.showToast = function showToast(message, type = 'success') {
        const container = ensureToastContainer();
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;

        container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('toast-show'));

        // Play audio feedback for certain toast types. Fail silently on autoplay/missing file.
        try {
            let src = null;
            if (type === 'success') src = '/static/success.mp3';
            else if (type === 'error') src = '/static/error.mp3';

            if (src) {
                const audio = new Audio(src);
                // .play() returns a promise; catch silently to avoid unhandled rejections
                audio.play().catch(() => {});
            }
        } catch (e) {
            // Ignore any errors creating/playing audio
        }

        setTimeout(() => {
            toast.classList.remove('toast-show');
            toast.classList.add('toast-hide');
            setTimeout(() => toast.remove(), 250);
        }, 3000);
    };

    // Global client-side error reporting to server to aid debugging in PyWebView
    function reportClientError(payload) {
        try {
            // Prefer sendBeacon for fire-and-forget, fallback to fetch
            const url = '/api/log_client_error';
            const body = JSON.stringify(payload || {});
            if (navigator && typeof navigator.sendBeacon === 'function') {
                const blob = new Blob([body], { type: 'application/json' });
                navigator.sendBeacon(url, blob);
                return;
            }
            fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }).catch(() => {});
        } catch (e) {
            // ignore
        }
    }

    window.addEventListener('error', function (ev) {
        try {
            const payload = { message: ev.message, filename: ev.filename, lineno: ev.lineno, colno: ev.colno, stack: ev.error && ev.error.stack };
            reportClientError(payload);
        } catch (e) {}
    });

    window.addEventListener('unhandledrejection', function (ev) {
        try {
            const reason = ev.reason;
            const payload = { message: reason && reason.message ? reason.message : String(reason), stack: reason && reason.stack };
            reportClientError(payload);
        } catch (e) {}
    });

    // Auto-retry/load patients when the window regains focus or becomes visible.
    (function ensurePatientsAutoReload() {
        let retryCount = 0;
        const maxRetries = 4; // try for a short window to avoid duplicate loads

        async function tryLoad() {
            try {
                const tbody = document.getElementById('patientTableBody');
                const emptyState = document.getElementById('emptyState');
                const table = document.getElementById('patientTable');

                const shouldLoad = (!tbody || tbody.children.length === 0) || (emptyState && emptyState.style.display !== 'none');
                if (!shouldLoad) return;

                if (typeof window.loadPatients === 'function') {
                    await window.loadPatients(document.getElementById('searchInput')?.value?.trim() || '');
                } else {
                    // fallback loader
                    if (typeof loadPatientsFallback === 'function') await loadPatientsFallback(document.getElementById('searchInput')?.value?.trim() || '');
                }
            } catch (err) {
                try { reportClientError({ phase: 'ensurePatientsAutoReload', error: String(err && err.stack ? err.stack : err) }); } catch (e) {}
            }
        }

        // Start retry loop after a short initial delay so initial DOMContentLoaded handlers finish first
        setTimeout(() => {
            const interval = setInterval(() => {
                if (retryCount++ >= maxRetries) { clearInterval(interval); return; }
                tryLoad();
            }, 5000);
        }, 2500);

        // Also trigger on focus and visibility change
        window.addEventListener('focus', tryLoad);
        document.addEventListener('visibilitychange', () => { if (!document.hidden) tryLoad(); });
    })();

    window.showConfirm = function showConfirm(message) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'confirm-overlay';

            const panel = document.createElement('div');
            panel.className = 'confirm-panel';

            const text = document.createElement('div');
            text.className = 'confirm-text';
            text.textContent = message;

            const actions = document.createElement('div');
            actions.className = 'confirm-actions';

            const cancelButton = document.createElement('button');
            cancelButton.type = 'button';
            cancelButton.className = 'btn btn-secondary';
            cancelButton.textContent = 'Cancel';

            const okButton = document.createElement('button');
            okButton.type = 'button';
            okButton.className = 'btn btn-danger';
            okButton.textContent = 'Yes';

            cancelButton.addEventListener('click', () => {
                overlay.remove();
                resolve(false);
            });

            okButton.addEventListener('click', () => {
                overlay.remove();
                resolve(true);
            });

            actions.appendChild(cancelButton);
            actions.appendChild(okButton);
            panel.appendChild(text);
            panel.appendChild(actions);
            overlay.appendChild(panel);
            document.body.appendChild(overlay);
            okButton.focus();
        });
    };

    window.openModal = function openModal(modalId, firstInputId) {
        if (typeof window.resetUiBlockingLayers === 'function') {
            window.resetUiBlockingLayers();
        }
        const modal = document.getElementById(modalId);
        if (!modal) return;

        modal.style.display = 'block';
        modal.classList.add('active');

        setTimeout(() => {
            const firstInput = document.getElementById(firstInputId);
            if (firstInput) {
                firstInput.focus();
                if (typeof firstInput.select === 'function') {
                    firstInput.select();
                }
            }
        }, 50);
    };

    window.resetUiBlockingLayers = window.resetUiBlockingLayers || function resetUiBlockingLayers() {
        try {
            document.querySelectorAll('.modal-overlay.active').forEach((overlay) => {
                overlay.classList.remove('active');
                overlay.style.display = 'none';
            });
            document.querySelectorAll('.modal-overlay').forEach((overlay) => {
                if (overlay.style.display === 'flex' || overlay.style.display === 'block') {
                    overlay.style.display = 'none';
                }
            });
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.pointerEvents = '';
        } catch (err) {
            console.error('resetUiBlockingLayers error', err);
        }
    };

    window.refreshPageAfterUiAction = window.refreshPageAfterUiAction || function refreshPageAfterUiAction(delay = 250) {
        try {
            window.clearTimeout(window.__uiRefreshTimer);
        } catch (e) {}
        window.__uiRefreshTimer = window.setTimeout(() => {
            try {
                window.location.reload();
            } catch (err) {
                console.error('refreshPageAfterUiAction error', err);
            }
        }, delay);
    };

    // Safe global closeModal to ensure modal close buttons always work
    window.closeModal = window.closeModal || function closeModal(modalId) {
        try {
            const modal = document.getElementById(modalId);
            if (!modal) return;
            modal.classList.remove('active');
            // hide after transition
            setTimeout(() => {
                try { modal.style.display = 'none'; } catch (e) {}
            }, 120);
            // If form inside modal, try to reset
            try {
                const form = modal.querySelector('form');
                if (form) form.reset();
            } catch (e) {}
            if (typeof window.resetUiBlockingLayers === 'function') {
                window.resetUiBlockingLayers();
            }
        } catch (err) {
            console.error('closeModal error', err);
            try { reportClientError({ phase: 'closeModal', error: String(err && err.stack ? err.stack : err) }); } catch (e) {}
        }
    };

    // Universal table sorter
    // tableId: id or selector for table element
    // columnIndex: zero-based column index
    // type: 'text' | 'number' | 'date' (optional, autodetect if omitted)
    window.sortTable = function sortTable(tableId, columnIndex, type, dir) {
        try {
            const table = typeof tableId === 'string' ? document.querySelector("#" + tableId) || document.querySelector(tableId) : tableId;
            if (!table) return;

            // Keep sort state on the table element
            table._sortState = table._sortState || { index: null, dir: 1 };

            // If explicit dir provided, use it (1 for asc, -1 for desc)
            if (typeof dir === 'number' && (dir === 1 || dir === -1)) {
                table._sortState.index = columnIndex;
                table._sortState.dir = dir;
            } else {
                // Toggle direction if same column
                if (table._sortState.index === columnIndex) table._sortState.dir = -table._sortState.dir;
                else { table._sortState.index = columnIndex; table._sortState.dir = 1; }
            }

            // Determine type if not provided
            const rows = Array.from(table.tBodies[0].rows);
            if (!type) {
                const sample = rows.find(r => r.cells.length > columnIndex && r.cells[columnIndex].textContent.trim() !== '');
                if (sample) {
                    const txt = sample.cells[columnIndex].textContent.trim();
                    if (/^\d{4}-\d{2}-\d{2}/.test(txt) || /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(txt)) type = 'date';
                    else if (!isNaN(Number(txt.replace(/[^0-9.-]/g, '')))) type = 'number';
                    else type = 'text';
                } else type = 'text';
            }

            const collator = new Intl.Collator(undefined, {numeric: type==='number', sensitivity: 'base'});

            rows.sort((a, b) => {
                const aCell = (a.cells[columnIndex] && a.cells[columnIndex].textContent.trim()) || '';
                const bCell = (b.cells[columnIndex] && b.cells[columnIndex].textContent.trim()) || '';

                if (type === 'number') {
                    const an = parseFloat(aCell.replace(/[^0-9.-]/g, '')) || 0;
                    const bn = parseFloat(bCell.replace(/[^0-9.-]/g, '')) || 0;
                    return (an - bn) * table._sortState.dir;
                }

                if (type === 'date') {
                    const ad = Date.parse(aCell) || 0;
                    const bd = Date.parse(bCell) || 0;
                    return (ad - bd) * table._sortState.dir;
                }

                // fallback to text
                return collator.compare(aCell, bCell) * table._sortState.dir;
            });

            // Rebuild tbody
            const tbody = table.tBodies[0];
            rows.forEach(r => tbody.appendChild(r));

            // Update header arrows
            const ths = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
            ths.forEach((th, idx) => {
                th.style.cursor = 'pointer';
                th.textContent = th.textContent.replace(/\s*[▲▼]$/,'');
                if (idx === columnIndex) th.textContent = th.textContent + (table._sortState.dir === 1 ? ' ▲' : ' ▼');
            });
        } catch (e) {
            // silently fail
            console.error('sortTable error', e);
        }
    };

    // Fallback: ensure register patient button opens modal even if page scripts had errors
    document.addEventListener('DOMContentLoaded', () => {
        try {
            const btn = document.getElementById('btnRegisterPatient');
            if (!btn) return;
            btn.addEventListener('click', (e) => {
                try {
                    const modal = document.getElementById('newPatientModal');
                    if (modal) modal.classList.add('active');
                    if (typeof openNewPatientModal === 'function') {
                        // try the original function as well
                        openNewPatientModal();
                    }
                } catch (err) {
                    console.error('Fallback openNewPatientModal error', err);
                }
            });
        } catch (err) {
            console.error('Error attaching fallback register handler', err);
        }
    });

    function safeSet(id, value) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = value;
        return el;
    }

    function safeText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
        return el;
    }

    async function fetchPatientFullRecord(patientId) {
        const response = await fetch(`/api/patients/${patientId}/full-record`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Failed to load patient record');
        }
        return response.json();
    }

    if (typeof window.openVisitModal !== 'function') {
        window.openVisitModal = async function openVisitModal(patientId, patientName) {
            try {
                const form = document.getElementById('newVisitForm');
                if (form) form.reset();
                safeText('visitPatientId', patientId);
                safeText('visitPatientName', patientName || '');
                safeSet('medicineList', '');
                safeText('prescriptionTotal', '0');

                window.medicineCounter = 0;
                window.currentPatientName = patientName || '';
                window.currentPatientContact = '';

                safeSet('patientDemographics', 'Loading...');
                safeSet('previousVisitsList', 'Loading...');

                const modal = document.getElementById('newVisitModal');
                if (modal) modal.classList.add('active');

                const data = await fetchPatientFullRecord(patientId);
                const patient = data.patient || {};
                const visits = Array.isArray(data.visits) ? data.visits : [];

                window.currentPatientContact = patient.contact || '';

                safeSet('patientDemographics', `
                    <div><strong>Age:</strong> ${patient.age || 'N/A'} years</div>
                    <div><strong>Gender:</strong> ${patient.gender || 'N/A'}</div>
                    <div><strong>Contact:</strong> ${patient.contact || 'N/A'}</div>
                    ${patient.height_cm ? `<div><strong>Height:</strong> ${patient.height_cm} cm</div>` : ''}
                    ${patient.weight_kg ? `<div><strong>Weight:</strong> ${patient.weight_kg} kg</div>` : ''}
                    ${patient.bmi ? `<div><strong>BMI:</strong> ${patient.bmi}</div>` : ''}
                    ${patient.bsr ? `<div><strong>BSR:</strong> ${patient.bsr}</div>` : ''}
                `);

                if (!visits.length) {
                    safeSet('previousVisitsList', `
                        <div style="text-align: center; color: var(--text-secondary); padding: 20px;">
                            <i class="fas fa-clipboard" style="font-size: 24px;"></i>
                            <p style="margin: 10px 0 0;">No previous visits</p>
                        </div>
                    `);
                } else {
                    safeSet('previousVisitsList', visits.map((visit, index) => {
                        const isExpanded = index === 0 ? 'open' : '';
                        return `
                            <details ${isExpanded} style="margin-bottom: 10px; background: var(--bg-surface); border-radius: 8px; padding: 10px;">
                                <summary style="cursor: pointer; font-weight: 600; color: var(--accent);">
                                    <i class="fas fa-calendar"></i> ${visit.date || ''}
                                </summary>
                                <div style="padding: 10px 0; border-top: 1px solid var(--border-color); margin-top: 10px;">
                                    ${visit.presenting_complaint ? `<div style="margin-bottom: 5px;"><strong>Complaint:</strong> ${visit.presenting_complaint}</div>` : ''}
                                    ${visit.treatment_plan ? `<div style="margin-bottom: 5px;"><strong>Treatment:</strong> ${visit.treatment_plan}</div>` : ''}
                                    ${Array.isArray(visit.prescriptions) && visit.prescriptions.length > 0 ? `
                                        <div style="margin-top: 8px; background: var(--bg-surface-2); padding: 8px; border-radius: 5px;">
                                            <strong style="color: var(--accent);"><i class="fas fa-pills"></i> Medicines:</strong>
                                            <ul style="margin: 5px 0 0 15px; padding: 0; font-size: 12px;">
                                                ${visit.prescriptions.map(p => `<li>${p.medicine_name} - ${p.dosage || ''} (Qty: ${p.quantity || 1})</li>`).join('')}
                                            </ul>
                                        </div>
                                    ` : ''}
                                </div>
                            </details>
                        `;
                    }).join(''));
                        }

                        // Prefill visit form vitals from latest visit or patient record
                        try {
                            const formEl = document.getElementById('newVisitForm');
                            if (formEl) {
                                const latest = visits && visits.length ? visits[0] : null;
                                const weightVal = (latest && latest.vitals_weight) ? latest.vitals_weight : (patient.weight_kg || '');
                                const bsrVal = (latest && latest.vitals_bsr) ? latest.vitals_bsr : (patient.bsr || '');
                                const bpVal = (latest && latest.vitals_bp) ? latest.vitals_bp : '';
                                const tempVal = (latest && latest.vitals_temp) ? latest.vitals_temp : '';

                                const wEl = document.getElementById('vitalsWeight'); if (wEl) wEl.value = weightVal;
                                const bsrEl = document.getElementById('vitalsBSR'); if (bsrEl) bsrEl.value = bsrVal;
                                const bpEl = document.getElementById('vitalsBP'); if (bpEl) bpEl.value = bpVal;
                                const tEl = document.getElementById('vitalsTemp'); if (tEl) tEl.value = tempVal;
                            }
                        } catch (e) {
                            // ignore prefill failures
                        }
                }
            } catch (err) {
                console.error('openVisitModal fallback error', err);
                reportClientError({ phase: 'openVisitModalFallback', error: String(err && err.stack ? err.stack : err) });
                showToast('Failed to open visit record', 'error');
            }
        };
    }

    if (typeof window.viewPatientRecord !== 'function') {
        window.viewPatientRecord = async function viewPatientRecord(patientId, patientName) {
            try {
                window.currentViewPatientId = patientId;
                safeText('historyPatientName', patientName || '');
                safeSet('viewPatientDetails', 'Loading...');
                safeSet('viewMedicalRecords', 'Loading...');
                safeSet('viewPharmacyRecords', 'Loading...');

                const modal = document.getElementById('historyModal');
                if (modal) modal.classList.add('active');

                const data = await fetchPatientFullRecord(patientId);
                const patient = data.patient || {};
                const visits = Array.isArray(data.visits) ? data.visits : [];

                safeSet('viewPatientDetails', `
                    <div><strong>ID:</strong> #${patient.id || patientId}</div>
                    <div><strong>Name:</strong> ${patient.name || patientName || ''}</div>
                    <div><strong>Age:</strong> ${patient.age || 'N/A'} years</div>
                    <div><strong>Gender:</strong> ${patient.gender || 'N/A'}</div>
                    <div><strong>Contact:</strong> ${patient.contact || 'N/A'}</div>
                    ${patient.height_cm ? `<div><strong>Height:</strong> ${patient.height_cm} cm</div>` : ''}
                    ${patient.weight_kg ? `<div><strong>Weight:</strong> ${patient.weight_kg} kg</div>` : ''}
                    ${patient.bmi ? `<div><strong>BMI:</strong> ${patient.bmi}</div>` : ''}
                    ${patient.bsr ? `<div><strong>BSR:</strong> ${patient.bsr}</div>` : ''}
                `);

                safeSet('viewMedicalRecords', visits.length ? visits.map(v => `
                    <div style="margin-bottom: 12px; padding: 12px; border: 1px solid var(--border-color); border-radius: 8px;">
                        <div><strong>Date:</strong> ${v.date || ''}</div>
                        <div><strong>Complaint:</strong> ${v.presenting_complaint || 'N/A'}</div>
                        <div><strong>Treatment:</strong> ${v.treatment_plan || 'N/A'}</div>
                    </div>
                `).join('') : '<div style="color: var(--text-secondary);">No medical records found.</div>');

                safeSet('viewPharmacyRecords', visits.length ? visits.flatMap(v => (v.prescriptions || []).map(rx => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 10px;">${v.date || ''}</td>
                        <td style="padding: 10px; font-weight: 600;">${rx.medicine_name || ''}</td>
                        <td style="padding: 10px; text-align: center;">${rx.quantity || 1}</td>
                        <td style="padding: 10px;">${rx.dosage || '-'}</td>
                        <td style="padding: 10px;">${rx.duration || '-'}</td>
                    </tr>
                `)).join('') : '<div style="color: var(--text-secondary);">No pharmacy records found.</div>');
            } catch (err) {
                console.error('viewPatientRecord fallback error', err);
                reportClientError({ phase: 'viewPatientRecordFallback', error: String(err && err.stack ? err.stack : err) });
                showToast('Failed to open patient record', 'error');
            }
        };
    }

    // Patients page fallback bootstrap. If the page's inline script fails to initialize,
    // this keeps the core register/list/PDF flow working.
    document.addEventListener('DOMContentLoaded', () => {
        try {
            const tbody = document.getElementById('patientTableBody');
            if (!tbody || window.__patientsFallbackBootstrapped) return;
            window.__patientsFallbackBootstrapped = true;

            const emptyState = document.getElementById('emptyState');
            const table = document.getElementById('patientTable') || document.querySelector('.patient-table');

            function escapeHtmlAttribute(value) {
                return String(value ?? '')
                    .replace(/&/g, '&amp;')
                    .replace(/"/g, '&quot;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
            }

            function showTableState(hasRows) {
                if (table) table.style.display = hasRows ? 'table' : 'none';
                if (emptyState) emptyState.style.display = hasRows ? 'none' : 'block';
            }

            function renderPatientsFallback(patientsRaw) {
                try {
                    let rows = [];
                    if (Array.isArray(patientsRaw)) rows = patientsRaw;
                    else if (patientsRaw && Array.isArray(patientsRaw.patients)) rows = patientsRaw.patients;
                    else if (patientsRaw && Array.isArray(patientsRaw.data)) rows = patientsRaw.data;

                    if (!rows.length) {
                        tbody.innerHTML = '';
                        showTableState(false);
                        return;
                    }

                    showTableState(true);

                    // Build HTML string first to avoid partial DOM updates on errors
                    const html = rows.map(patient => {
                        const id = patient.id ?? '';
                        const name = String(patient.name || '').replace(/'/g, "\\'");
                        const age = (patient.age === null || patient.age === undefined) ? '-' : patient.age;
                        const gender = patient.gender || '-';
                        const contact = patient.contact || '-';
                        const address = (patient.address || '-') .toString().replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        const last_visit = patient.last_visit || 'Never';

                        return `
                            <tr>
                                <td>#${id}</td>
                                <td><strong>${name}</strong></td>
                                <td>${age}</td>
                                <td>${gender}</td>
                                <td>${contact}</td>
                                <td title="${address}" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${address}</td>
                                <td>${last_visit}</td>
                                <td>
                                    <button type="button" class="btn-action btn-view" data-action="view" data-patient-id="${id}" data-patient-name="${escapeHtmlAttribute(name)}">
                                        <i class="fas fa-eye"></i> View
                                    </button>
                                    <button type="button" class="btn-action btn-visit" data-action="visit" data-patient-id="${id}" data-patient-name="${escapeHtmlAttribute(name)}">
                                        <i class="fas fa-plus"></i> Add Visit
                                    </button>
                                    <button type="button" class="btn-action btn-delete" data-action="delete" data-patient-id="${id}" data-patient-name="${escapeHtmlAttribute(name)}" title="Delete Patient">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }).join('');

                    tbody.innerHTML = html;
                    if (!tbody.__actionsBound) {
                        tbody.__actionsBound = true;
                        tbody.addEventListener('click', async (event) => {
                            const button = event.target.closest('button[data-action]');
                            if (!button || !tbody.contains(button)) return;

                            const action = button.dataset.action;
                            const patientId = parseInt(button.dataset.patientId, 10);
                            const patientName = button.dataset.patientName || '';

                            try {
                                if (action === 'view') {
                                    await window.viewPatientRecord(patientId, patientName);
                                } else if (action === 'visit') {
                                    await window.openVisitModal(patientId, patientName);
                                } else if (action === 'delete' && typeof window.deletePatient === 'function') {
                                    await window.deletePatient(patientId, patientName);
                                }
                            } catch (err) {
                                console.error('Fallback patient table action failed', err);
                                showToast('Action failed, please try again', 'error');
                            }
                        });
                    }
                } catch (err) {
                    console.error('renderPatientsFallback error', err);
                    // Keep previous content on render errors and report
                    reportClientError({ phase: 'renderPatientsFallback', error: String(err && err.stack ? err.stack : err) });
                }
            }

            async function loadPatientsFallback(query = '') {
                try {
                    const response = await fetch(`/api/patients?search=${encodeURIComponent(query)}`);
                    const json = await response.json().catch(() => null);
                    const patients = Array.isArray(json) ? json : (json && (json.patients || json.data)) || [];
                    renderPatientsFallback(patients);
                } catch (error) {
                    console.error('Fallback loadPatients failed:', error);
                    reportClientError({ phase: 'loadPatientsFallback', error: String(error && error.stack ? error.stack : error) });
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Failed to load patients</td></tr>';
                    showTableState(true);
                }
            }

            window.loadPatients = window.loadPatients || loadPatientsFallback;

            if (!window.openNewPatientModal) {
                window.openNewPatientModal = function () {
                    const form = document.getElementById('newPatientForm');
                    const modal = document.getElementById('newPatientModal');
                    if (form) form.reset();
                    // Date field removed from form; date will be set automatically on server/PDF generation
                    const bmi = document.getElementById('patientBmi');
                    if (bmi) bmi.value = '';
                    if (modal) modal.classList.add('active');
                };
            }

            if (!window.saveNewPatient) {
                window.saveNewPatient = async function (event) {
                    event.preventDefault();
                    const form = event.target;
                    const payload = {
                        name: form.name.value,
                        age: parseInt(form.age.value, 10),
                        contact: form.contact.value,
                        gender: form.gender.value || null,
                        height_cm: parseFloat(form.height_cm?.value) || null,
                        weight_kg: parseFloat(form.weight_kg?.value) || null,
                        bmi: form.bmi?.value ? parseFloat(form.bmi.value) : null,
                        bsr: form.bsr ? form.bsr.value || null : null
                    };

                    try {
                        const response = await fetch('/api/patients', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });

                        if (!response.ok) {
                            const error = await response.json().catch(() => ({}));
                            throw new Error(error.detail || 'Failed to save patient');
                        }

                        const modal = document.getElementById('newPatientModal');
                        if (modal) modal.classList.remove('active');
                        await loadPatientsFallback(document.getElementById('searchInput')?.value?.trim() || '');
                        showToast('Patient registered successfully!', 'success');
                        if (typeof window.refreshPageAfterUiAction === 'function') {
                            window.refreshPageAfterUiAction();
                        }
                    } catch (error) {
                        console.error('Fallback saveNewPatient failed:', error);
                        showToast(error.message || 'Failed to save patient', 'error');
                    }
                };
            }

            if (!window.printNewPatientPdf) {
                window.printNewPatientPdf = async function () {
                    const form = document.getElementById('newPatientForm');
                    if (!form) return;

                    const heightInput = form.querySelector('input[name="height_cm"]');
                    const weightInput = form.querySelector('input[name="weight_kg"]');
                    const payload = {
                        pt_name: form.name.value || '',
                        age: form.age.value || '',
                        contact: form.contact.value || '',
                        date: new Date().toISOString().slice(0, 10),
                        ht_wt: (heightInput?.value || weightInput?.value) ? `${(window.cleanNumericValue ? window.cleanNumericValue(heightInput?.value) : heightInput?.value) || '-'} cm / ${(window.cleanNumericValue ? window.cleanNumericValue(weightInput?.value) : weightInput?.value) || '-'} kg` : '',
                        bmi: form.bmi.value || '',
                        rbs: form.bsr ? form.bsr.value || '' : ''
                    };

                    try {
                        // Create patient and initial visit automatically
                        const initial_visit = {
                            vitals_bp: form.vitals_bp?.value || null,
                            vitals_weight: form.vitals_weight?.value ? parseFloat(form.vitals_weight.value) : (form.weight_kg?.value ? parseFloat(form.weight_kg.value) : null),
                            vitals_temp: form.vitals_temp?.value ? parseFloat(form.vitals_temp.value) : null,
                            vitals_bsr: form.bsr ? form.bsr.value || null : null,
                            vitals_spo2: form.vitals_spo2?.value || null,
                            vitals_heart_rate: form.vitals_heart_rate?.value || null,
                            presenting_complaint: null,
                            examination: null,
                            differentials: null,
                            treatment_plan: null,
                            consultation_fee: 0,
                            medicines: []
                        };

                        const saveResponse = await fetch('/api/patients', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                name: form.name.value,
                                age: parseInt(form.age.value, 10),
                                contact: form.contact.value,
                                gender: form.gender.value || null,
                                height_cm: form.height_cm?.value ? parseFloat(form.height_cm.value) : null,
                                weight_kg: form.weight_kg?.value ? parseFloat(form.weight_kg.value) : null,
                                bmi: form.bmi?.value ? parseFloat(form.bmi.value) : null,
                                bsr: form.bsr ? form.bsr.value || null : null,
                                create_visit: true,
                                initial_visit: initial_visit
                            })
                        });

                        if (!saveResponse.ok) {
                            const error = await saveResponse.json().catch(() => ({}));
                            throw new Error(error.detail || 'Failed to save patient');
                        }

                        const result = await saveResponse.json().catch(() => ({}));
                        const pdfPayload = {
                            patient_id: result.patient_id || null,
                            pt_name: form.name.value || '',
                            age: form.age.value || '',
                            sex: form.gender.value || '',
                            contact: form.contact.value || '',
                            date: new Date().toISOString().slice(0, 10),
                            height_cm: form.height_cm?.value || '',
                            weight_kg: form.weight_kg?.value || '',
                            ht_wt: (heightInput?.value || weightInput?.value) ? `${(window.cleanNumericValue ? window.cleanNumericValue(heightInput?.value) : heightInput?.value) || '-'} cm / ${(window.cleanNumericValue ? window.cleanNumericValue(weightInput?.value) : weightInput?.value) || '-'} kg` : '',
                            bmi: form.bmi.value || '',
                            rbs: form.bsr ? form.bsr.value || '' : '',
                            presenting_complaint: '',
                            medical_examination: '',
                            investigation_advised: '',
                            provisional_diagnosis: '',
                            special_note: '',
                            medicines: []
                        };

                        const pdfResponse = await fetch('/api/print_prescription', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(pdfPayload)
                        });

                        if (!pdfResponse.ok) {
                            const error = await pdfResponse.json().catch(() => ({}));
                            throw new Error(error.detail || 'Failed to generate PDF');
                        }

                        const modal = document.getElementById('newPatientModal');
                        if (modal) modal.classList.remove('active');
                        await loadPatientsFallback(document.getElementById('searchInput')?.value?.trim() || '');
                        showToast('Patient saved and PDF generated.', 'success');
                        if (typeof window.refreshPageAfterUiAction === 'function') {
                            window.refreshPageAfterUiAction();
                        }
                    } catch (error) {
                        console.error('Fallback printNewPatientPdf failed:', error);
                        showToast(error.message || 'Failed to generate PDF', 'error');
                    }
                };
            }

            const searchInput = document.getElementById('searchInput');
            if (searchInput && !searchInput.__fallbackBound) {
                searchInput.__fallbackBound = true;
                searchInput.addEventListener('input', debounce((e) => loadPatientsFallback(e.target.value.trim()), 300));
            }

            // Only run the fallback loader if the table is still empty — avoid duplicating the main loader
            try {
                const tbody = document.getElementById('patientTableBody');
                const shouldRunFallback = !tbody || tbody.children.length === 0;
                if (shouldRunFallback) {
                    loadPatientsFallback(searchInput?.value?.trim() || '');
                }
            } catch (e) {
                // best-effort fallback invocation
                loadPatientsFallback(searchInput?.value?.trim() || '');
            }
        } catch (err) {
            console.error('Patients fallback bootstrap failed', err);
        }
    });
})();