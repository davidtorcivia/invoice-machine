/**
 * @typedef {{ description: string, quantity: number, unit_price: string | number, unit_type: string }} LineItemDraft
 * @typedef {{
 *   id?: number|string,
 *   client_id: string | number,
 *   name: string,
 *   frequency: string,
 *   schedule_day: string | number,
 *   schedule_month: string | number,
 *   quarter_month: string | number,
 *   currency_code: string,
 *   payment_terms_days: string | number,
 *   notes: string,
 *   line_items: LineItemDraft[],
 *   is_active: boolean,
 *   tax_enabled: boolean | null,
 *   tax_rate: string | number,
 *   tax_name: string,
 *   show_payment_instructions: boolean,
 *   selected_payment_methods: string[],
 *   auto_email_enabled: boolean,
 *   email_subject_template: string,
 *   email_body_template: string,
 *   use_default_notes: boolean
 * }} ScheduleFormData
 * @typedef {{
 *   id: number|string,
 *   client_id: number|string,
 *   name: string,
 *   frequency: string,
 *   schedule_day: number,
 *   schedule_month?: number,
 *   quarter_month?: number,
 *   currency_code: string,
 *   payment_terms_days: number,
 *   notes?: string,
 *   line_items?: LineItemDraft[],
 *   is_active: boolean,
 *   tax_enabled: boolean | null,
 *   tax_rate?: string | number,
 *   tax_name?: string,
 *   show_payment_instructions?: boolean,
 *   selected_payment_methods?: string[],
 *   auto_email_enabled?: boolean,
 *   email_subject_template?: string,
 *   email_body_template?: string,
 *   use_default_notes?: boolean,
 *   client_name?: string,
 *   client_business?: string,
 *   next_invoice_date?: string
 * }} RecurringSchedule
 */

export const weekdayOptions = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' }
];

export const quarterMonthOptions = [
  { value: 1, label: '1st month (Jan, Apr, Jul, Oct)' },
  { value: 2, label: '2nd month (Feb, May, Aug, Nov)' },
  { value: 3, label: '3rd month (Mar, Jun, Sep, Dec)' }
];

export const monthOptions = [
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' }
];

/** @returns {ScheduleFormData} */
export function createScheduleFormData() {
  return {
    client_id: '',
    name: '',
    frequency: 'monthly',
    schedule_day: 1,
    schedule_month: 1,
    quarter_month: 1,
    currency_code: 'USD',
    payment_terms_days: 30,
    notes: '',
    line_items: [],
    is_active: true,
    tax_enabled: null,
    tax_rate: '',
    tax_name: 'Tax',
    show_payment_instructions: true,
    selected_payment_methods: [],
    auto_email_enabled: false,
    email_subject_template: '',
    email_body_template: '',
    use_default_notes: true
  };
}

/**
 * @param {RecurringSchedule} schedule
 * @returns {ScheduleFormData}
 */
export function createScheduleFormDataFromSchedule(schedule) {
  return {
    client_id: schedule.client_id,
    name: schedule.name,
    frequency: schedule.frequency,
    schedule_day: schedule.schedule_day,
    schedule_month: schedule.schedule_month || 1,
    quarter_month: schedule.quarter_month || 1,
    currency_code: schedule.currency_code,
    payment_terms_days: schedule.payment_terms_days,
    notes: schedule.notes || '',
    line_items: schedule.line_items ? [...schedule.line_items] : [],
    is_active: schedule.is_active,
    tax_enabled: schedule.tax_enabled,
    tax_rate: schedule.tax_rate || '',
    tax_name: schedule.tax_name || 'Tax',
    show_payment_instructions: schedule.show_payment_instructions !== false,
    selected_payment_methods: schedule.selected_payment_methods || [],
    auto_email_enabled: schedule.auto_email_enabled || false,
    email_subject_template: schedule.email_subject_template || '',
    email_body_template: schedule.email_body_template || '',
    use_default_notes: schedule.use_default_notes !== false
  };
}

/**
 * @param {ScheduleFormData} formData
 */
export function buildSchedulePayload(formData) {
  return {
    ...formData,
    client_id: Number(formData.client_id),
    schedule_day: Number(formData.schedule_day),
    schedule_month: formData.frequency === 'yearly' ? Number(formData.schedule_month) : null,
    quarter_month: formData.frequency === 'quarterly' ? Number(formData.quarter_month) : 1,
    payment_terms_days: Number(formData.payment_terms_days),
    tax_rate: formData.tax_enabled && formData.tax_rate ? Number(formData.tax_rate) : null,
    notes: formData.use_default_notes ? '' : formData.notes
  };
}

/**
 * @param {string} frequency
 */
export function formatFrequency(frequency) {
  const labels = {
    daily: 'Daily',
    weekly: 'Weekly',
    monthly: 'Monthly',
    quarterly: 'Quarterly',
    yearly: 'Yearly'
  };
  return labels[frequency] || frequency;
}

/**
 * @param {string | undefined} dateStr
 */
export function formatScheduleDate(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString();
}
