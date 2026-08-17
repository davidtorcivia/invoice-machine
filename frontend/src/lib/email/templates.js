export const placeholderDescriptions = [
  { code: '{invoice_number}', description: 'The invoice or quote number' },
  { code: '{quote_number}', description: 'Same as invoice_number' },
  { code: '{document_type}', description: '"Invoice" or "Quote"' },
  { code: '{document_type_lower}', description: '"invoice" or "quote"' },
  { code: '{client_name}', description: "Client's contact name" },
  { code: '{client_business_name}', description: "Client's business name" },
  { code: '{client_email}', description: "Client's email" },
  { code: '{total} / {amount}', description: 'Formatted total' },
  { code: '{subtotal}', description: 'Formatted subtotal' },
  { code: '{amount_due}', description: 'Formatted outstanding balance' },
  { code: '{amount_paid}', description: 'Formatted amount already paid' },
  { code: '{payment_link}', description: 'Hosted payment URL, if one exists' },
  { code: '{due_date}', description: 'Due date as "Month DD, YYYY"' },
  { code: '{issue_date}', description: 'Issue date as "Month DD, YYYY"' },
  { code: '{your_name}', description: 'Your name from the business profile' },
  { code: '{business_name}', description: 'Your business name from the profile' },
  { code: '{line_items}', description: 'Comma-separated line item descriptions' }
];
