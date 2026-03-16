export function withBase(input: string): string {
  if (!input) return input;

  if (
    input.startsWith('http://') ||
    input.startsWith('https://') ||
    input.startsWith('mailto:') ||
    input.startsWith('tel:') ||
    input.startsWith('#') ||
    input.startsWith('data:')
  ) {
    return input;
  }

  const base = import.meta.env.BASE_URL || '/';
  const cleanBase = base.endsWith('/') ? base : `${base}/`;
  const cleanInput = input.replace(/^\/+/, '');
  return `${cleanBase}${cleanInput}`;
}

export function stripBase(pathname: string): string {
  const base = import.meta.env.BASE_URL || '/';
  if (base === '/' || !pathname.startsWith(base)) {
    return pathname;
  }

  const rest = pathname.slice(base.length);
  return `/${rest}`.replace(/\/+/g, '/');
}
