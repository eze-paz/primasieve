module.exports = {
  testDir: ".",
  timeout: 30000,
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
};
