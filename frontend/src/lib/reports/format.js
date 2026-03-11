export const reportSummaryCards = [
  { key: 'invoiced', label: 'Total Invoiced', icon: 'invoice', tone: 'invoiced' },
  { key: 'paid', label: 'Total Paid', icon: 'check', tone: 'paid' },
  { key: 'outstanding', label: 'Outstanding', icon: 'clock', tone: 'outstanding' },
  { key: 'overdue', label: 'Overdue', icon: 'warning', tone: 'overdue' }
];

/**
 * @param {string | number} value
 * @param {string | number} max
 */
export function getBarWidth(value, max) {
  if (!max || max === 0) return 0;
  return Math.min((Number(value) / Number(max)) * 100, 100);
}
