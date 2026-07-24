/**
 * Shapes returned by the REST API.
 *
 * These mirror the serializers in `invoice_machine/presenters.py`, which are the
 * single source of truth for what the API emits. `tests/test_api_contract.py`
 * compares the two and fails if a field is added on one side only, so these
 * typedefs cannot quietly drift out of date.
 *
 * Money arrives as a decimal string rather than a number: the backend works in
 * Decimal and JSON numbers are floats, so parsing early would reintroduce the
 * rounding error the backend exists to avoid. Parse at the point of display.
 *
 * @see invoice_machine/presenters.py
 */

/**
 * @typedef {Object} InvoiceItem
 * @property {number} id
 * @property {string} description
 * @property {string} quantity      Decimal string, trailing zeros trimmed
 * @property {string} unit_type     "qty" or "hours"
 * @property {string} unit_price    Decimal string
 * @property {string} total         Decimal string
 * @property {number} sort_order
 */

/**
 * @typedef {Object} Invoice
 * @property {number} id
 * @property {string} invoice_number
 * @property {string} document_type            "invoice" or "quote"
 * @property {number|null} client_id
 * @property {string|null} client_name
 * @property {string|null} client_business
 * @property {string|null} client_address
 * @property {string|null} client_email
 * @property {string|null} client_reference
 * @property {string} status                   draft|sent|paid|overdue|cancelled
 * @property {string|null} paid_at
 * @property {string} issue_date
 * @property {string|null} due_date
 * @property {number} payment_terms_days
 * @property {string} currency_code
 * @property {string} subtotal                 Decimal string
 * @property {boolean} tax_enabled
 * @property {string} tax_rate                 Decimal string
 * @property {string} tax_name
 * @property {string} tax_amount               Decimal string
 * @property {string} total                    Decimal string
 * @property {string} amount_paid              Decimal string
 * @property {string} amount_due               Decimal string, never negative
 * @property {boolean} is_partially_paid
 * @property {string|null} exchange_rate       Rate into base_currency_code
 * @property {string|null} base_currency_code
 * @property {number|null} converted_from_invoice_id
 * @property {number|null} converted_to_invoice_id
 * @property {string|null} payment_link_url
 * @property {string|null} payment_link_created_at
 * @property {string|null} last_reminder_sent_at
 * @property {number[]} reminders_sent          Day offsets already sent
 * @property {string|null} notes
 * @property {boolean} show_payment_instructions
 * @property {string|string[]|null} selected_payment_methods
 * @property {string|null} pdf_path
 * @property {string|null} pdf_generated_at
 * @property {string} created_at
 * @property {string} updated_at
 * @property {string|null} deleted_at
 * @property {number} line_items_count
 * @property {string} [line_items_preview]
 * @property {InvoiceItem[]} items
 */

/**
 * @typedef {Object} Client
 * @property {number} id
 * @property {string|null} name
 * @property {string|null} business_name
 * @property {string} display_name
 * @property {string|null} address_line1
 * @property {string|null} address_line2
 * @property {string|null} city
 * @property {string|null} state
 * @property {string|null} postal_code
 * @property {string|null} country
 * @property {string|null} email
 * @property {string|null} phone
 * @property {number} payment_terms_days
 * @property {string|null} notes
 * @property {number|null} tax_enabled          null means inherit the global default
 * @property {string|number|null} tax_rate
 * @property {string|null} tax_name
 * @property {string|null} preferred_currency
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 * @property {string|null} deleted_at
 */

/**
 * @typedef {Object} Payment
 * @property {number} id
 * @property {number} invoice_id
 * @property {string} amount                   Decimal string
 * @property {string} currency_code            Snapshot of the invoice currency
 * @property {string} payment_date
 * @property {string|null} method
 * @property {string|null} reference
 * @property {string|null} notes
 * @property {string|null} provider            Set for provider webhooks, e.g. "stripe"
 * @property {string|null} external_id
 * @property {string} created_at
 */

/**
 * @typedef {Object} RecurringSchedule
 * @property {number} id
 * @property {number} client_id
 * @property {string|null} client_name
 * @property {string|null} client_business
 * @property {string} name
 * @property {string} frequency                daily|weekly|monthly|quarterly|yearly
 * @property {number} schedule_day
 * @property {number|null} schedule_month      Calendar month for yearly schedules
 * @property {number} quarter_month            Which month of the quarter, 1-3
 * @property {string} currency_code
 * @property {number} payment_terms_days
 * @property {string|null} notes
 * @property {boolean} use_default_notes
 * @property {Array<Record<string, any>>} line_items
 * @property {boolean} show_payment_instructions
 * @property {string[]} selected_payment_methods
 * @property {boolean} auto_email_enabled
 * @property {string|null} email_subject_template
 * @property {string|null} email_body_template
 * @property {boolean|null} tax_enabled
 * @property {string|number|null} tax_rate
 * @property {string|null} tax_name
 * @property {boolean} is_active
 * @property {string} next_invoice_date
 * @property {number|null} last_invoice_id
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * The profile as returned by `GET /api/profile`.
 *
 * Note this comes from `BusinessProfileSchema` in `api/profile.py`, not from
 * `serialize_business_profile`. The endpoint declares a response_model, which
 * filters the payload, so the Pydantic schema is what the SPA actually sees.
 * Secrets such as SMTP and Stripe credentials are deliberately absent; only
 * their presence is exposed, through the dedicated settings endpoints.
 *
 * @typedef {Object} BusinessProfile
 * @property {number} id
 * @property {string} name
 * @property {string|null} business_name
 * @property {string|null} address_line1
 * @property {string|null} address_line2
 * @property {string|null} city
 * @property {string|null} state
 * @property {string|null} postal_code
 * @property {string} country
 * @property {string|null} email
 * @property {string|null} phone
 * @property {string|null} ein
 * @property {string|null} logo_path
 * @property {string} accent_color
 * @property {number} default_payment_terms_days
 * @property {string} default_currency_code
 * @property {string|null} default_notes
 * @property {string|null} default_payment_instructions
 * @property {string|null} payment_methods    JSON string of [{id, name, instructions}]
 * @property {string} theme_preference
 * @property {boolean} mcp_api_key_configured
 * @property {boolean} bot_api_key_configured
 * @property {string|null} app_base_url
 * @property {boolean} default_tax_enabled
 * @property {string|null} default_tax_rate
 * @property {string} default_tax_name
 * @property {string} created_at
 * @property {string} updated_at
 */

export {};
