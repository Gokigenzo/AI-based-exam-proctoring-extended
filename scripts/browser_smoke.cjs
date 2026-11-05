/* Optional browser integration test: npm install --no-save playwright,
   set EXAMWATCH_URL to a server using an isolated EXAMWATCH_DATA directory. */
const {chromium}=require('playwright');
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const audioFixture=fs.existsSync(path.join(root,'.tmp/fixtures/vi-clean.wav'))?'vi-clean.wav':'speech.wav';
  const browser=await chromium.launch({channel:'chrome',headless:true,args:[
    '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
    `--use-file-for-fake-video-capture=${path.join(root,'.tmp/fixtures/camera.y4m')}`,
    `--use-file-for-fake-audio-capture=${path.join(root,'.tmp/fixtures',audioFixture)}`,
  ]});
  const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['camera','microphone']});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(process.env.EXAMWATCH_URL||'http://127.0.0.1:8001');
    const base=process.env.EXAMWATCH_URL||'http://127.0.0.1:8001';
    const existing=await(await page.request.get(base+'/api/students')).json();
    if(existing.some(s=>s.id==='FIXTURE001'))await page.request.delete(base+'/api/students/FIXTURE001');
    await page.locator('#connect-camera').click();
    await page.waitForFunction(()=>document.getElementById('video').videoWidth>0);
    await page.locator('[data-page="students"]').click();
    await page.locator('#student-id').fill('FIXTURE001');
    await page.locator('#student-name').fill('Thí sinh thử nghiệm');
    for(let i=0;i<3;i++)await page.locator('#take-sample').click();
    const enrolled=page.waitForResponse(r=>r.url().endsWith('/api/students')&&r.request().method()==='POST');
    await page.locator('#save-student').click();
    assert.equal((await enrolled).status(),201);
    await page.waitForFunction(()=>document.getElementById('student-list').textContent.includes('FIXTURE001'));
    await page.locator('[data-page="monitor"]').click();
    await page.locator('#session-title').fill('Browser integration fixture');
    await page.locator('#start-session').click();
    await page.waitForFunction(()=>document.getElementById('known-count').textContent==='1',{},{timeout:60000});
    const calibration=page.waitForResponse(r=>r.url().endsWith('/api/calibrate'));
    await page.locator('#calibrate').click();
    assert.equal((await calibration).status(),200);
    await page.screenshot({path:path.join(root,'.tmp/browser-live.png'),fullPage:true});
    const row=await page.evaluate(async()=>{const s=await(await fetch('/api/status')).json();return s.session;});
    const deadline=Date.now()+45000;
    let hasTranscript=false;
    while(Date.now()<deadline){
      const data=await(await page.request.get(base+'/api/sessions/'+row.id)).json();
      if(data.transcripts.length>0){hasTranscript=true;break;}
      await new Promise(r=>setTimeout(r,1000));
    }
    assert(hasTranscript,'No transcript persisted within 45 seconds');
    await page.locator('#stop-session').click();
    await page.waitForFunction(()=>document.getElementById('session-state').textContent==='CHƯA BẮT ĐẦU');
    await page.locator('[data-page="history"]').click();
    await page.locator('[data-session]').first().click();
    await page.waitForFunction(()=>document.getElementById('history-detail').textContent.includes('Thí sinh thử nghiệm'));
    const result=await page.evaluate(async(id)=>await(await fetch('/api/sessions/'+id)).json(),row.id);
    assert(result.session.ended_at);
    assert(result.observations.length>0);
    assert(result.transcripts.length>0);
    await page.setViewportSize({width:390,height:844});
    await page.locator('[data-page="monitor"]').click();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(root,'.tmp/browser-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const report={registered:true,identityMatched:true,calibration:true,microphoneWorklet:true,
      transcriptCount:result.transcripts.length,observationCount:result.observations.length,
      sessionEnded:true,mobileOverflow:false,browserErrors:errors};
    fs.writeFileSync(path.join(root,'.tmp/browser-smoke.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
