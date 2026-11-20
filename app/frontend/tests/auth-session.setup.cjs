const path = require("node:path");
const { pathToFileURL } = require("node:url");

module.exports = async () => {
  const root = path.resolve(__dirname, "..");
  const { build } = await import(pathToFileURL(path.join(root, "node_modules/vite/dist/node/index.js")).href);
  await build({
    configFile: false,
    root,
    envDir: __dirname,
    publicDir: false,
    define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify("/api") },
    build: {
      outDir: path.resolve(root, "../../generated/auth-session-20261120/dist"),
      emptyOutDir: false,
      rollupOptions: {
        input: {
          main: path.join(root, "index.html"),
          "auth-session-api": path.join(root, "src/api.js"),
          "auth-session-harness": path.join(__dirname, "auth-session.harness.jsx"),
          "auth-session-drafts": path.join(root, "src/utils/documentIntakeDrafts.js"),
        },
        preserveEntrySignatures: "strict",
        output: {
          entryFileNames: entry => entry.name.startsWith("auth-session-")
            ? "[name].js" : "assets/[name]-[hash].js",
        },
      },
    },
  });
};
