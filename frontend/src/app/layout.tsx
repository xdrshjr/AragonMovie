import type { Metadata, Viewport } from 'next';
import '@/app/globals.css';
import '@/styles/apple-theme.css';

export const metadata: Metadata = {
  title: 'AI Movie Generator',
  description: 'Create stunning videos with AI',
  keywords: ['AI', 'video generation', 'movie maker', 'artificial intelligence'],
};

/**
 * Lock the browser UI (form controls, scrollbars, caret) to the dark palette so
 * native widgets match the gray-black surfaces instead of rendering white.
 */
export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0A0A0B',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // `dark` is permanent: the app is dark-only, and the class keeps every
    // existing `dark:` utility in the components meaningful.
    <html lang="en" className="dark">
      <body className="antialiased bg-background text-text-primary">
        {children}
      </body>
    </html>
  );
}
