import { test, expect } from '@playwright/test';


test('test', async ({ page }) => {

  const first_url = 'https://mypage.sso.biglobe.ne.jp/';
  const timeout = 60000;

  const user_id = '★ユーザID★';
  const password = '★パスワード★';

  await test.step('move-login-console', async () => {
    await page.goto(first_url);
    await page.waitForLoadState('load', { timeout });
    await page.screenshot({
      path: "./screenshot/001.png",
      fullPage: true,
    });
  });

  await test.step('move-login-console', async () => {
    await page.locator('a').filter({ hasText: 'ログインする' }).click();
    await page.waitForLoadState('load', { timeout });
    await page.screenshot({
      path: "./screenshot/002.png",
      fullPage: true,
    });
  });

  await test.step('login-campaign-console', async () => {
    await page.getByRole('textbox', { name: 'メールアドレスまたはユーザID' }).fill(user_id);
    await page.getByRole('textbox', { name: 'BIGLOBEパスワード' }).fill(password);
    await page.locator('#submit').click();
    await page.waitForLoadState('load', { timeout });
    await page.screenshot({
      path: "./screenshot/003.png",
      fullPage: true,
    });
  });

  await test.step('login-campaign-console', async () => {
    await page.getByRole('link', { name: 'ご契約内容' }).click();
    await page.screenshot({
      path: "./screenshot/004.png",
      fullPage: true,
    });
  });
});
