import { defineConfig } from '@playwright/test';
export default defineConfig({
 testDir:'scripts',testMatch:'planner.e2e.spec.ts',timeout:90000,workers:1,
 use:{baseURL:process.env.CC_PREVIEW_URL??'http://127.0.0.1:4182',viewport:{width:1440,height:1000},
  launchOptions:{executablePath:process.env.CC_CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--use-angle=swiftshader','--enable-unsafe-swiftshader']}},
 reporter:'list',outputDir:'test-results',
});
