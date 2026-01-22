# Invoice Machine Frontend

Svelte frontend for the Invoice Machine invoicing application.

## Development

```bash
npm install
npm run dev
```

The dev server runs on port 3000 and proxies API requests to the backend on port 8080.

## Build

```bash
npm run build
```

Built files are output to `dist/`, which the backend serves as static files.

## Tech Stack

- **Svelte 5** - UI framework
- **SvelteKit** - Application framework (static adapter)
- **Vite** - Build tool
- **Tailwind-like CSS** - Custom utility classes (no build step)
