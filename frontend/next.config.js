/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // `standalone` emits a self-contained server.js + minimal node_modules tree,
  // which is exactly what the Electron desktop shell ships and runs.
  output: 'standalone',
  images: {
    domains: [
      'localhost',
      // Add your image service domains here
      'cdn.example.com',
      'ark.cn-beijing.volces.com',
      'api.nanobananapro.com',
      'api.kuai.host',
    ],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
      {
        protocol: 'http',
        hostname: 'localhost',
      },
      {
        protocol: 'http',
        hostname: '127.0.0.1',
      },
    ],
  },
  // Enable experimental features if needed
  experimental: {
    // Add any experimental features here
  },
  // Logging configuration
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
};

module.exports = nextConfig;
