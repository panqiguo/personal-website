const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'numeric',
  day: 'numeric',
  year: 'numeric'
});

export function formatDate(date: Date): string {
  const parts = DATE_FORMATTER.formatToParts(date);
  const month = parts.find((part) => part.type === 'month')?.value ?? '';
  const day = parts.find((part) => part.type === 'day')?.value ?? '';
  const year = parts.find((part) => part.type === 'year')?.value ?? '';
  return `${month}-${day}, ${year}`;
}
