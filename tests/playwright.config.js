module.exports = {
  testDir: '.',
  testMatch: 'smoke.spec.js',
  use: {
    baseURL: 'http://localhost:8765',
    headless: true,
    browserName: 'chromium',
  },
  reporter: [['line']],
};
