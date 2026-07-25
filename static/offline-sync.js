// ─────────────────────────────────────────────────────────────────────────────
// TripBudgetMonitor — Offline Sync Manager
// Stores pending expenses in IndexedDB when offline.
// Automatically syncs when the user comes back online.
// ─────────────────────────────────────────────────────────────────────────────

const OFFLINE_SYNC_DB   = 'tbm-offline-sync';
const OFFLINE_SYNC_VER  = 1;
const PENDING_STORE     = 'pending_expenses';

// ── IndexedDB helpers ─────────────────────────────────────────────────────────

function openSyncDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_SYNC_DB, OFFLINE_SYNC_VER);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(PENDING_STORE)) {
        const store = db.createObjectStore(PENDING_STORE, {
          keyPath: 'local_id',
          autoIncrement: true,
        });
        store.createIndex('trip_id', 'trip_id', { unique: false });
        store.createIndex('synced', 'synced', { unique: false });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

async function savePendingExpense(tripId, formData) {
  const db = await openSyncDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(PENDING_STORE, 'readwrite');
    const store = tx.objectStore(PENDING_STORE);
    const record = {
      trip_id:      tripId,
      synced:       false,
      created_at:   new Date().toISOString(),
      // serialise all text fields (no receipt blobs for offline — user is notified)
      title:        formData.get('title') || '',
      amount:       formData.get('amount') || '',
      paid_by:      formData.get('paid_by') || '',
      category:     formData.get('category') || '',
      custom_category: formData.get('custom_category') || '',
      payment_mode: formData.get('payment_mode') || '',
      description:  formData.get('description') || '',
      merchant_name: formData.get('merchant_name') || '',
      gst_amount:   formData.get('gst_amount') || '',
      is_recurring: formData.get('is_recurring') === 'on' ? 'on' : '',
      recurrence_type: formData.get('recurrence_type') || '',
    };
    const addReq = store.add(record);
    addReq.onsuccess = (e) => resolve(e.target.result);  // returns local_id
    addReq.onerror   = (e) => reject(e.target.error);
  });
}

async function getPendingExpenses(tripId = null) {
  const db = await openSyncDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(PENDING_STORE, 'readonly');
    const store = tx.objectStore(PENDING_STORE);
    const req   = store.getAll();
    req.onsuccess = (e) => {
      let rows = e.target.result.filter(r => !r.synced);
      if (tripId !== null) rows = rows.filter(r => r.trip_id == tripId);
      resolve(rows);
    };
    req.onerror = (e) => reject(e.target.error);
  });
}

async function markSynced(localId) {
  const db = await openSyncDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(PENDING_STORE, 'readwrite');
    const store = tx.objectStore(PENDING_STORE);
    const getReq = store.get(localId);
    getReq.onsuccess = (e) => {
      const record = e.target.result;
      if (record) {
        record.synced = true;
        store.put(record);
      }
      resolve();
    };
    getReq.onerror = (e) => reject(e.target.error);
  });
}

// ── Sync pending expenses to server ──────────────────────────────────────────

async function syncPendingExpenses() {
  if (!navigator.onLine) return;

  const pending = await getPendingExpenses();
  if (pending.length === 0) return;

  console.log(`[OfflineSync] Syncing ${pending.length} pending expense(s)…`);

  // Get CSRF token from cookie
  function getCookie(name) {
    const val = document.cookie
      .split('; ')
      .find(row => row.startsWith(name + '='));
    return val ? decodeURIComponent(val.split('=')[1]) : '';
  }

  let syncedCount = 0;
  let failCount   = 0;

  for (const expense of pending) {
    const body = new URLSearchParams();
    [
      'title', 'amount', 'paid_by', 'category', 'custom_category',
      'payment_mode', 'description', 'merchant_name', 'gst_amount',
      'is_recurring', 'recurrence_type',
    ].forEach(field => body.append(field, expense[field] || ''));
    body.append('offline_created_at', expense.created_at);

    try {
      const res = await fetch(`/trip/${expense.trip_id}/sync-offline-expense/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: body.toString(),
      });

      if (res.ok) {
        await markSynced(expense.local_id);
        syncedCount++;
      } else {
        failCount++;
        console.warn('[OfflineSync] Server rejected expense', expense.local_id, res.status);
      }
    } catch (err) {
      failCount++;
      console.warn('[OfflineSync] Network error syncing expense', expense.local_id, err);
    }
  }

  // Show a subtle toast notification
  if (syncedCount > 0) {
    showSyncToast(syncedCount, failCount);
  }

  // Reload page data if we are on the dashboard or view-expenses page
  const path = window.location.pathname;
  if (syncedCount > 0 && (path.includes('/dashboard/') || path.includes('/view-expenses/'))) {
    setTimeout(() => window.location.reload(), 1500);
  }
}

// ── Toast notification ────────────────────────────────────────────────────────

function showSyncToast(synced, failed) {
  // Remove existing toast
  document.getElementById('tbm-sync-toast')?.remove();

  const toast = document.createElement('div');
  toast.id = 'tbm-sync-toast';

  const msg = failed === 0
    ? `✅ ${synced} offline expense${synced > 1 ? 's' : ''} synced!`
    : `✅ ${synced} synced · ⚠️ ${failed} failed`;

  toast.textContent = msg;
  Object.assign(toast.style, {
    position:     'fixed',
    bottom:       '80px',
    left:         '50%',
    transform:    'translateX(-50%)',
    background:   '#10b981',
    color:        '#fff',
    padding:      '12px 24px',
    borderRadius: '50px',
    fontWeight:   '600',
    fontSize:     '0.9rem',
    zIndex:       '9999',
    boxShadow:    '0 4px 20px rgba(0,0,0,0.2)',
    transition:   'opacity 0.4s ease',
    whiteSpace:   'nowrap',
  });

  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; }, 3000);
  setTimeout(() => toast.remove(), 3500);
}

// ── Pending badge on add-expense link ────────────────────────────────────────

async function updatePendingBadge(tripId) {
  const pending = await getPendingExpenses(tripId);
  const count   = pending.length;

  // Remove old badge
  document.querySelectorAll('.tbm-offline-badge').forEach(el => el.remove());

  if (count === 0) return;

  const badge = document.createElement('span');
  badge.className = 'tbm-offline-badge';
  badge.textContent = count;
  Object.assign(badge.style, {
    display:      'inline-flex',
    alignItems:   'center',
    justifyContent: 'center',
    minWidth:     '20px',
    height:       '20px',
    background:   '#ef4444',
    color:        '#fff',
    borderRadius: '50px',
    fontSize:     '0.72rem',
    fontWeight:   '700',
    padding:      '0 5px',
    marginLeft:   '6px',
    verticalAlign: 'middle',
  });

  // Try to attach to nav link for "Add Expense"
  const addLinks = document.querySelectorAll('a[href*="add-expense"]');
  addLinks.forEach(link => link.appendChild(badge.cloneNode(true)));
}

// ── Auto-sync on page load and online event ───────────────────────────────────

window.addEventListener('online', () => {
  console.log('[OfflineSync] Back online — syncing…');
  syncPendingExpenses();
});

// Try to sync when page loads (covers case where user was offline then refreshed)
document.addEventListener('DOMContentLoaded', () => {
  if (navigator.onLine) {
    syncPendingExpenses();
  }
});

// Export helpers for use in add_expense page
window.TBMOfflineSync = {
  savePendingExpense,
  getPendingExpenses,
  syncPendingExpenses,
  updatePendingBadge,
  showSyncToast,
};
