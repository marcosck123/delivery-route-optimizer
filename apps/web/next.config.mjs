/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // permite rodar em container sem copiar node_modules inteiro (Docker/Vercel)
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
};

export default nextConfig;
