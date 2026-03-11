export const sortOptions = [
  { value: 'issue_date-desc', label: 'Date (newest)', field: 'issue_date', dir: 'desc' },
  { value: 'issue_date-asc', label: 'Date (oldest)', field: 'issue_date', dir: 'asc' },
  { value: 'due_date-desc', label: 'Due Date (newest)', field: 'due_date', dir: 'desc' },
  { value: 'due_date-asc', label: 'Due Date (oldest)', field: 'due_date', dir: 'asc' },
  { value: 'client-asc', label: 'Client (A-Z)', field: 'client', dir: 'asc' },
  { value: 'client-desc', label: 'Client (Z-A)', field: 'client', dir: 'desc' },
  { value: 'invoice_number-desc', label: 'Invoice # (newest)', field: 'invoice_number', dir: 'desc' },
  { value: 'invoice_number-asc', label: 'Invoice # (oldest)', field: 'invoice_number', dir: 'asc' },
  { value: 'total-desc', label: 'Total (high-low)', field: 'total', dir: 'desc' },
  { value: 'total-asc', label: 'Total (low-high)', field: 'total', dir: 'asc' },
  { value: 'status-asc', label: 'Status (A-Z)', field: 'status', dir: 'asc' }
];

export const statusConfig = {
  draft: { class: 'badge-draft', label: 'Draft' },
  sent: { class: 'badge-sent', label: 'Sent' },
  paid: { class: 'badge-paid', label: 'Paid' },
  overdue: { class: 'badge-overdue', label: 'Overdue' },
  cancelled: { class: 'badge-cancelled', label: 'Cancelled' }
};

export const yearOptions = Array.from({ length: 6 }, (_, index) => new Date().getFullYear() - index);

/**
 * @param {{ status: string, document_type?: string }} invoice
 */
export function getNormalizedStatus(invoice) {
  if (invoice.document_type === 'quote' && ['paid', 'overdue'].includes(invoice.status)) {
    return 'sent';
  }
  return invoice.status;
}

/**
 * @param {{ status: string, due_date?: string, document_type?: string }} invoice
 */
export function isOverdue(invoice) {
  if (invoice.document_type === 'quote') {
    return false;
  }
  if (invoice.status === 'paid' || invoice.status === 'cancelled' || invoice.status === 'draft') {
    return false;
  }
  if (!invoice.due_date) return false;
  const dueDate = new Date(invoice.due_date);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return dueDate < today;
}

/**
 * @param {{ status: string, due_date?: string, document_type?: string }} invoice
 */
export function getEffectiveStatus(invoice) {
  const normalizedStatus = getNormalizedStatus(invoice);
  if (isOverdue(invoice) && invoice.status !== 'overdue') {
    return 'overdue';
  }
  return normalizedStatus;
}

export function getBulkActionLabel(action) {
  return {
    mark_sent: 'Mark as Sent',
    mark_paid: 'Mark as Paid',
    delete: 'Delete'
  }[action] || action;
}

/**
 * @param {string | null} action
 * @param {Array<{ status: string }>} selectedInvoices
 * @param {number} count
 */
export function getBulkActionMessage(action, selectedInvoices, count) {
  switch (action) {
    case 'mark_sent': {
      const draftCount = selectedInvoices.filter((invoice) => invoice.status === 'draft').length;
      const skipped = count - draftCount;
      return `Mark ${draftCount} draft invoice${draftCount !== 1 ? 's' : ''} as sent?${skipped > 0 ? ` (${skipped} non-draft will be skipped)` : ''}`;
    }
    case 'mark_paid': {
      const eligibleCount = selectedInvoices.filter((invoice) => ['sent', 'overdue'].includes(invoice.status)).length;
      const skipped = count - eligibleCount;
      return `Mark ${eligibleCount} invoice${eligibleCount !== 1 ? 's' : ''} as paid?${skipped > 0 ? ` (${skipped} ineligible will be skipped)` : ''}`;
    }
    case 'delete':
      return `Move ${count} invoice${count !== 1 ? 's' : ''} to trash? You can restore them later.`;
    default:
      return `Apply action to ${count} invoice${count !== 1 ? 's' : ''}?`;
  }
}
