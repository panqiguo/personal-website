import { defineCollection, z } from 'astro:content';

const postSchema = z.object({
  title: z.string().optional(),
  date: z.coerce.date().optional(),
  summary: z.string().optional(),
  featured: z.boolean().optional(),
  tags: z.array(z.string()).optional()
});

const posts = defineCollection({
  type: 'content',
  schema: postSchema
});

const games = defineCollection({
  type: 'content',
  schema: ({ image }) =>
    z.object({
      title: z.string(),
      href: z.string().url(),
      summary: z.string(),
      cover: image(),
      featured: z.boolean().default(false),
      date: z.coerce.date().optional()
    })
});

export const collections = { posts, games };
