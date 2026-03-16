const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric'
});

export function formatDate(date: Date): string {
  return DATE_FORMATTER.format(date);
}
