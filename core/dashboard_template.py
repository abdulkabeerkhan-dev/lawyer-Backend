# Quarantine Review Dashboard HTML Template
# Served by FastAPI at /admin/quarantine/dashboard

def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quarantine Review & Curation Dashboard | Section AI</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background-color: #0b1120; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    .card { background-color: #1e293b; border: 1px solid #334155; }
    .input-field { background-color: #0f172a; border: 1px solid #334155; color: #f8fafc; font-size: 0.85rem; padding: 0.45rem 0.65rem; border-radius: 0.375rem; width: 100%; }
    .input-field:focus { border-color: #3b82f6; outline: none; }
  </style>
</head>
<body class="p-6 min-h-screen">
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- Header Section -->
    <header class="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-slate-800 pb-5 gap-4">
      <div>
        <div class="flex items-center gap-2.5">
          <span class="px-2 py-0.5 text-xs font-bold uppercase tracking-wider rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
            Human-in-the-Loop Gatekeeper
          </span>
          <span class="text-xs text-emerald-400 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Quarantine Isolation Active
          </span>
        </div>
        <h1 class="text-2xl font-bold mt-2 text-white">Quarantine Review & Promotion Dashboard</h1>
        <p class="text-xs text-slate-400 mt-1">Physical human curation screen. Inspect official source documents, correct extracted metadata inline, and sign off promotions into full_judgments.</p>
      </div>

      <!-- Human Reviewer Session Bar -->
      <div class="flex items-center gap-3 bg-slate-900 border border-slate-800 p-2.5 rounded-xl">
        <span class="text-xs text-slate-400 font-semibold">Reviewer:</span>
        <input type="text" id="reviewer-name" placeholder="Enter your name / initials" value="" class="bg-slate-800 text-xs px-2.5 py-1.5 rounded border border-slate-700 text-white w-44 focus:border-amber-500 focus:outline-none">
        <button onclick="fetchRecords()" class="px-3 py-1.5 text-xs font-semibold rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition">
          🔄 Refresh
        </button>
      </div>
    </header>

    <!-- Metrics Bar -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="card p-4 rounded-xl">
        <div class="text-xs font-medium text-slate-400">Pending Human Review</div>
        <div class="text-2xl font-bold mt-1 text-amber-400" id="stat-pending">0</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Requires physical sign-off</div>
      </div>
      <div class="card p-4 rounded-xl">
        <div class="text-xs font-medium text-slate-400">Promoted to full_judgments</div>
        <div class="text-2xl font-bold mt-1 text-emerald-400" id="stat-promoted">0</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Verified & indexed</div>
      </div>
      <div class="card p-4 rounded-xl">
        <div class="text-xs font-medium text-slate-400">Rejected / Malformed</div>
        <div class="text-2xl font-bold mt-1 text-rose-400" id="stat-rejected">0</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Purged from pipeline</div>
      </div>
      <div class="card p-4 rounded-xl">
        <div class="text-xs font-medium text-slate-400">Direct CLI Promotion</div>
        <div class="text-2xl font-bold mt-1 text-purple-400">LOCKED</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Requires Dashboard Session</div>
      </div>
    </div>

    <!-- Alert / Toast Container -->
    <div id="toast-container" class="space-y-2"></div>

    <!-- Records Container -->
    <div id="records-list" class="space-y-5">
      <div class="text-center py-12 text-slate-500 text-sm">Loading quarantine records...</div>
    </div>
  </div>

  <script>
    let allRecords = [];

    function showToast(msg, type = 'info') {
      const c = document.getElementById('toast-container');
      const t = document.createElement('div');
      const bg = type === 'success' ? 'bg-emerald-950 border-emerald-800 text-emerald-300' :
                 type === 'error' ? 'bg-rose-950 border-rose-800 text-rose-300' :
                 'bg-slate-900 border-slate-700 text-slate-300';
      t.className = `p-3 rounded-lg border text-xs font-medium flex justify-between items-center ${bg}`;
      t.innerHTML = `<span>${msg}</span><button onclick="this.parentElement.remove()" class="ml-4 font-bold">&times;</button>`;
      c.appendChild(t);
      setTimeout(() => { if (t.parentElement) t.remove(); }, 6000);
    }

    async function fetchRecords() {
      const container = document.getElementById('records-list');
      try {
        const res = await fetch('/admin/quarantine/records');
        const data = await res.json();
        if (data.status !== 'success') throw new Error(data.detail || 'Fetch failed');

        allRecords = data.records || [];
        updateStats();
        renderRecords();
      } catch (err) {
        container.innerHTML = `<div class="text-center py-12 text-rose-400 text-sm">Error loading records: ${err.message}</div>`;
      }
    }

    function updateStats() {
      const pending = allRecords.filter(r => r.status === 'pending_review').length;
      const promoted = allRecords.filter(r => r.status === 'promoted').length;
      const rejected = allRecords.filter(r => r.status === 'rejected').length;
      document.getElementById('stat-pending').textContent = pending;
      document.getElementById('stat-promoted').textContent = promoted;
      document.getElementById('stat-rejected').textContent = rejected;
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function renderRecords() {
      const container = document.getElementById('records-list');
      if (allRecords.length === 0) {
        container.innerHTML = '<div class="text-center py-12 text-slate-500 text-sm">No quarantined records found.</div>';
        return;
      }

      container.innerHTML = allRecords.map((r, idx) => {
        const isPending = r.status === 'pending_review';
        const isPromoted = r.status === 'promoted';
        const isRejected = r.status === 'rejected';

        const statusBadge = isPending
          ? '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">Pending Review</span>'
          : isPromoted
          ? `<span class="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Promoted: ${escapeHtml(r.promoted_to_case_id || '')}</span>`
          : '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">Rejected</span>';

        const titleVal = escapeHtml(r.case_title || r.extracted_case_title || '');
        const courtVal = escapeHtml(r.court_name || r.extracted_court_name || '');
        const docketVal = escapeHtml(r.docket_number || '');
        const typeVal = escapeHtml(r.case_type || 'CP');
        const dateVal = escapeHtml(r.decision_date || r.extracted_date || '');
        const citationVal = escapeHtml(r.neutral_citation || r.extracted_citation || '');
        const benchVal = escapeHtml(r.bench || r.extracted_judge_names || '');
        const rawText = escapeHtml((r.raw_text || '').slice(0, 2000));

        let domain = '';
        try {
          if (r.source_url) {
            domain = new URL(r.source_url).hostname.replace('www.', '');
          }
        } catch (e) {}

        const isPartial = r.is_partial || r.content_type === 'partial' || (r.text_health_score !== null && r.text_health_score !== undefined && r.text_health_score < 0.8);
        const dynamicBadge = isPartial
          ? `<div class="p-2 rounded-lg bg-amber-950/60 border border-amber-800/80 text-amber-300 text-xs flex items-center justify-between gap-2 font-medium">
              <span>⚠️ Partial document — full text extraction incomplete.</span>
              <a href="${escapeHtml(r.source_url)}" target="_blank" class="underline font-semibold hover:text-amber-100 flex-shrink-0">Read the complete judgment at the original source →</a>
            </div>`
          : r.source_url
          ? `<div class="p-2 rounded-lg bg-sky-950/60 border border-sky-800/80 text-sky-300 text-xs flex items-center justify-between gap-2 font-medium">
              <span>Retrieved directly from <strong>${escapeHtml(domain || 'Official Court Portal')}</strong> — not yet in our full verified index.</span>
              <a href="${escapeHtml(r.source_url)}" target="_blank" class="underline font-semibold hover:text-sky-100 flex-shrink-0">View original source →</a>
            </div>`
          : '';

        return `
          <div class="card rounded-xl p-5 space-y-4 border ${isPromoted ? 'border-emerald-800' : isRejected ? 'border-rose-900' : 'border-slate-700'}" id="card-${r.id}">
            <div class="flex flex-col md:flex-row md:items-center justify-between pb-3 border-b border-slate-800 gap-2">
              <div class="flex items-center gap-2.5 flex-wrap">
                <span class="font-mono font-bold text-sm text-slate-200">#${idx + 1}</span>
                <span class="px-2 py-0.5 text-xs rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">${courtVal || 'Court'}</span>
                <span class="text-xs font-mono font-semibold text-slate-300">${docketVal || 'No Docket'}</span>
                ${statusBadge}
              </div>

              <!-- Official Source Document Link -->
              <a href="${escapeHtml(r.source_url)}" target="_blank" class="text-xs text-sky-400 hover:text-sky-300 underline flex items-center gap-1 font-medium">
                📄 Open Official Source Document ↗
              </a>
            </div>

            <!-- Dynamic State Badge -->
            ${dynamicBadge}

            <!-- Editable Metadata Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-xs">
              <div class="space-y-1 md:col-span-2">
                <label class="font-semibold text-slate-400 flex justify-between">
                  <span>Case Title (Reviewer must verify and clean):</span>
                  <span class="text-[11px] text-amber-400 font-normal">Verify party names & strip trailing artifacts</span>
                </label>
                <input type="text" id="input-title-${r.id}" value="${titleVal}" ${!isPending ? 'disabled' : ''} class="input-field font-semibold text-slate-100">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Court Name:</label>
                <input type="text" id="input-court-${r.id}" value="${courtVal}" ${!isPending ? 'disabled' : ''} class="input-field">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Docket Number:</label>
                <input type="text" id="input-docket-${r.id}" value="${docketVal}" ${!isPending ? 'disabled' : ''} class="input-field">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Case Type Code (Canonical):</label>
                <input type="text" id="input-type-${r.id}" value="${typeVal}" ${!isPending ? 'disabled' : ''} class="input-field font-mono">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Decision / Order Date:</label>
                <input type="text" id="input-date-${r.id}" value="${dateVal}" ${!isPending ? 'disabled' : ''} class="input-field font-mono">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Neutral Citation / Label:</label>
                <input type="text" id="input-citation-${r.id}" value="${citationVal}" ${!isPending ? 'disabled' : ''} class="input-field">
              </div>

              <div class="space-y-1">
                <label class="font-semibold text-slate-400">Bench / Judges:</label>
                <input type="text" id="input-bench-${r.id}" value="${benchVal}" ${!isPending ? 'disabled' : ''} class="input-field">
              </div>
            </div>

            <!-- Collapsible Text Preview -->
            <details class="bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs">
              <summary class="cursor-pointer text-slate-400 hover:text-slate-200 font-semibold">
                🔍 View Extracted Judgment Text (First 2,000 chars)
              </summary>
              <pre class="mt-2 text-[11px] text-slate-300 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto bg-slate-950 p-2.5 rounded border border-slate-800">${rawText || 'No text extracted.'}</pre>
            </details>

            ${r.reviewed_by ? `
              <div class="text-[11px] text-slate-400 bg-slate-900 p-2.5 rounded border border-slate-800 flex justify-between">
                <span>Reviewed by: <strong class="text-slate-200">${escapeHtml(r.reviewed_by)}</strong> on ${r.reviewed_at || 'N/A'}</span>
                ${r.rejection_reason ? `<span class="text-rose-400">Reason: ${escapeHtml(r.rejection_reason)}</span>` : ''}
              </div>
            ` : ''}

            <!-- Human Action Controls -->
            ${isPending ? `
              <div class="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
                <button onclick="handleReject('${r.id}')" class="px-4 py-2 rounded-lg bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 text-xs font-semibold transition">
                  ❌ Reject Record
                </button>
                <button onclick="handleApprove('${r.id}')" class="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition shadow flex items-center gap-1.5">
                  ✅ Physical Sign-Off & Promote to full_judgments
                </button>
              </div>
            ` : ''}
          </div>
        `;
      }).join('');
    }

    async function handleApprove(recordId) {
      const reviewerInput = document.getElementById('reviewer-name');
      const reviewerName = reviewerInput.value.trim();
      if (!reviewerName) {
        reviewerInput.focus();
        showToast('Please enter your name/initials in the Reviewer box at top before approving.', 'error');
        return;
      }

      const editedFields = {
        case_title: document.getElementById(`input-title-${recordId}`).value.trim(),
        court_name: document.getElementById(`input-court-${recordId}`).value.trim(),
        docket_number: document.getElementById(`input-docket-${recordId}`).value.trim(),
        case_type: document.getElementById(`input-type-${recordId}`).value.trim(),
        decision_date: document.getElementById(`input-date-${recordId}`).value.trim(),
        neutral_citation: document.getElementById(`input-citation-${recordId}`).value.trim(),
        bench: document.getElementById(`input-bench-${recordId}`).value.trim()
      };

      if (!confirm(`Confirm Human Approval:\nReviewer: ${reviewerName}\nTitle: ${editedFields.case_title}\n\nPromote this record into production full_judgments?`)) {
        return;
      }

      try {
        const res = await fetch('/admin/quarantine/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            record_id: recordId,
            action: 'approve',
            reviewer_name: reviewerName,
            edited_fields: editedFields
          })
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || 'Approval failed');

        showToast(`✅ Successfully promoted to full_judgments! Case ID: ${result.canonical_id}`, 'success');
        fetchRecords();
      } catch (err) {
        showToast(`Approval Error: ${err.message}`, 'error');
      }
    }

    async function handleReject(recordId) {
      const reviewerInput = document.getElementById('reviewer-name');
      const reviewerName = reviewerInput.value.trim();
      if (!reviewerName) {
        reviewerInput.focus();
        showToast('Please enter your name/initials in the Reviewer box at top before rejecting.', 'error');
        return;
      }

      const reason = prompt('Please enter the reason for rejection (e.g., corrupt PDF, mismatched docket, invalid court):');
      if (!reason || !reason.trim()) {
        showToast('Rejection cancelled: reason is required.', 'info');
        return;
      }

      try {
        const res = await fetch('/admin/quarantine/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            record_id: recordId,
            action: 'reject',
            reviewer_name: reviewerName,
            rejection_reason: reason.trim()
          })
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || 'Rejection failed');

        showToast(`Record marked as rejected.`, 'info');
        fetchRecords();
      } catch (err) {
        showToast(`Rejection Error: ${err.message}`, 'error');
      }
    }

    // Auto-fetch on load
    fetchRecords();
  </script>
</body>
</html>
"""
