import { getCollection, type CollectionEntry } from 'astro:content';
import { access, readFile, stat } from 'node:fs/promises';
import path from 'node:path';

type PostOverride = {
  title?: string;
  date?: string;
  summary?: string;
  featured?: boolean;
  tags?: string[];
};

type PostOverrides = Record<string, PostOverride>;

export type SitePost = {
  slug: string;
  path: string;
  title: string;
  date: Date;
  summary?: string;
  featured: boolean;
  tags: string[];
  section: '散文' | '摘录' | '未分类';
  entry: CollectionEntry<'posts'>;
};

const POSTS_DIR = path.join(process.cwd(), 'src/content/posts');
const META_FILE = path.join(process.cwd(), 'src/content/posts-meta.json');

function titleFromEntryId(id: string): string {
  const normalized = id.endsWith('/index') ? id.slice(0, -6) : id;
  return path.basename(normalized).replace(/\.md$/i, '');
}

function sectionFromEntryId(id: string): SitePost['section'] {
  const [firstSegment] = id.split('/');
  if (firstSegment === '散文' || firstSegment === '摘录') return firstSegment;
  return '未分类';
}

function publicPathFromSlug(slug: string, section: SitePost['section']): string {
  const prefix = `${section}/`;
  if ((section === '散文' || section === '摘录') && slug.startsWith(prefix)) {
    return slug.slice(prefix.length);
  }
  return slug;
}

function safeDate(input?: string): Date | null {
  if (!input) return null;
  const date = new Date(input);
  return Number.isNaN(date.getTime()) ? null : date;
}

async function loadOverrides(): Promise<PostOverrides> {
  try {
    const raw = await readFile(META_FILE, 'utf-8');
    return JSON.parse(raw) as PostOverrides;
  } catch {
    return {};
  }
}

async function resolveSourceFile(entry: CollectionEntry<'posts'>): Promise<string | null> {
  const candidates = [
    path.join(POSTS_DIR, `${entry.id}.md`),
    path.join(POSTS_DIR, entry.id, 'index.md'),
    path.join(POSTS_DIR, `${entry.slug}.md`),
    path.join(POSTS_DIR, entry.slug, 'index.md')
  ];

  for (const filePath of candidates) {
    try {
      await access(filePath);
      return filePath;
    } catch {
      // Continue.
    }
  }

  return null;
}

async function defaultDate(entry: CollectionEntry<'posts'>): Promise<Date> {
  const source = await resolveSourceFile(entry);
  if (!source) return new Date();

  const fileStats = await stat(source);
  if (fileStats.birthtimeMs > 0) {
    return fileStats.birthtime;
  }
  return fileStats.mtime;
}

export async function getSitePosts(): Promise<SitePost[]> {
  const [entries, overrides] = await Promise.all([
    getCollection('posts'),
    loadOverrides()
  ]);

  const mapped = await Promise.all(
    entries.map(async (entry) => {
      const baseTitle = titleFromEntryId(entry.id);
      const section = sectionFromEntryId(entry.id);
      const override = overrides[entry.slug] ?? overrides[baseTitle] ?? {};
      const fallbackDate = await defaultDate(entry);
      const date =
        safeDate(override.date) ??
        (entry.data.date instanceof Date ? entry.data.date : fallbackDate);

      return {
        slug: entry.slug,
        path: publicPathFromSlug(entry.slug, section),
        title: override.title ?? entry.data.title ?? baseTitle,
        date,
        summary: override.summary ?? entry.data.summary,
        featured: override.featured ?? entry.data.featured ?? false,
        tags: override.tags ?? entry.data.tags ?? [],
        section,
        entry
      } satisfies SitePost;
    })
  );

  mapped.sort((a, b) => {
    if (a.featured !== b.featured) return a.featured ? -1 : 1;
    return b.date.getTime() - a.date.getTime();
  });

  return mapped;
}

export async function getPostsBySection(section: Extract<SitePost['section'], '散文' | '摘录'>) {
  const posts = await getSitePosts();
  return posts.filter((post) => post.section === section);
}
