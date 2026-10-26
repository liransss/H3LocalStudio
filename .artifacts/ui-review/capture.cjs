const {chromium}=require('./browser-tools/node_modules/playwright-core');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1050}});
 await page.goto('http://127.0.0.1:1420');
 await page.getByRole('button',{name:'Create',exact:true}).click();
 await page.getByRole('button',{name:'Generate mock video',exact:true}).waitFor({state:'visible'});
 await page.locator('.recent-filmstrip button').filter({hasText:'cute white service robot'}).first().click();
 await page.locator('.page-content').evaluate(el=>el.scrollTo(0,0));
 await page.screenshot({path:'.artifacts/ui-review/after-create-final.png'});
 for(const width of [1280,768,390,320]){
  await page.setViewportSize({width,height:900});
  await page.locator('.page-content').evaluate(el=>el.scrollTo(0,0));
  await page.screenshot({path:`.artifacts/ui-review/after-create-final-${width}.png`});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 }
 const nav=await page.locator('.main-nav button').evaluateAll(items=>items.map(el=>({label:el.textContent,y:el.getBoundingClientRect().y,margin:getComputedStyle(el).marginTop})));
 console.log(JSON.stringify(nav));
 await page.setViewportSize({width:1600,height:1050});
 await page.locator('.page-content').evaluate(el=>el.scrollTo(0,500));
 await page.getByRole('button',{name:'History',exact:true}).click();
 assert.equal(await page.locator('.page-content').evaluate(el=>el.scrollTop),0);
 await browser.close();
 console.log('PASS: final screenshot review, responsive overflow, navigation scroll reset.');
})().catch(e=>{console.error(e);process.exit(1)});
