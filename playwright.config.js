const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'./e2e',timeout:30000,use:{baseURL:process.env.LEADFINDER_TEST_URL||'http://127.0.0.1:8788',channel:'chrome',headless:true},reporter:'list',workers:1});
