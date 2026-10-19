import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests', timeout:90000, expect:{timeout:20000}, workers:1,
 use:{baseURL:process.env.WEB_URL || 'http://127.0.0.1:3000', viewport:{width:1440,height:1000}, trace:'off', screenshot:'only-on-failure'},
 reporter:[['list'],['html',{open:'never'}]]});
