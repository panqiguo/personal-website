import { defineConfig } from 'astro/config';
import remarkGfm from 'remark-gfm';
import remarkFootnotes from './src/lib/remark-footnotes.mjs';
import remarkImageSize from './src/lib/remark-image-size.mjs';

const repo = process.env.GITHUB_REPOSITORY?.split('/')[1] ?? '';
const owner = process.env.GITHUB_REPOSITORY_OWNER ?? '';
const isUserSite = repo.endsWith('.github.io');
const base = process.env.GITHUB_ACTIONS && repo && !isUserSite ? `/${repo}` : '/';
const site =
  process.env.SITE_URL ||
  (owner ? `https://${owner}.github.io` : 'https://example.com');

export default defineConfig({
  site,
  base,
  markdown: {
    remarkPlugins: [remarkGfm, remarkImageSize, remarkFootnotes]
  },
  image: {
    service: {
      entrypoint: 'astro/assets/services/noop'
    }
  }
});
