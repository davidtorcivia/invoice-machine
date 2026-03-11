export const placeholderDescriptions = [
  { code: '{invoice_number}', description: 'The invoice or quote number (e.g., INV-20250119-1)' },
  { code: '{document_type}', description: '"Invoice" or "Quote"' },
  { code: '{document_type_lower}', description: '"invoice" or "quote" (lowercase)' },
  { code: '{client_name}', description: "Client's contact name" },
  { code: '{client_business_name}', description: "Client's business name" },
  { code: '{total} / {amount}', description: 'Formatted total amount (e.g., $1,234.56)' },
  { code: '{due_date}', description: 'Due date formatted as "Month DD, YYYY"' },
  { code: '{issue_date}', description: 'Issue date formatted as "Month DD, YYYY"' },
  { code: '{your_name}', description: 'Your name from business profile' },
  { code: '{business_name}', description: 'Your business name from profile' },
  { code: '{line_items}', description: 'Comma-separated list of line item descriptions' }
];
