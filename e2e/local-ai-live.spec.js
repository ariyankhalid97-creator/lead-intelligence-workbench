const { test, expect } = require('@playwright/test');

test('optional read-only check of installed local AI and dashboard', async ({page, request}) => {
  test.skip(process.env.LEADFINDER_LIVE_AI !== '1', 'Explicit live local-AI availability check only');
  const response = await request.get('/api/ai/status');
  expect(response.ok()).toBeTruthy();
  const status = await response.json();
  expect(status.available).toBeTruthy();
  expect(status.models.some(m => m.name === 'qwen3.5:4b')).toBeTruthy();
  expect(status.models.every(m => !/embed|cloud/i.test(m.name))).toBeTruthy();
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  await expect(page.locator('#aiStatus')).toContainText('Local AI is ready');
  await expect(page.getByLabel('Local model', {exact:true})).toHaveValue(status.default_model);
  await expect(page.getByRole('button', {name:'Suggest search terms',exact:true})).toBeEnabled();
  await page.screenshot({path:'replica/clone-screens/local-ai-live.png'});
});
