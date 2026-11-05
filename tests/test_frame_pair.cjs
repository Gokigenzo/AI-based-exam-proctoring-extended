const {test}=require('node:test');
const assert=require('node:assert/strict');
const {FramePair}=require('../web/frame-pair.js');

test('renders each result on its captured image even while live person moves', async()=>{
  const pair=new FramePair(), painted=[];
  const canvas={width:0,height:0,getContext:()=>({drawImage:(image)=>painted.push(image.id)})};
  const imageA={id:'person-left',width:960,height:720,close(){}}, imageB={id:'person-right',width:1280,height:720,close(){}};
  await pair.accept('jpeg-A',[{bbox:[.1,.2,.2,.3]}],async()=>imageA);
  const resultA=pair.paint(canvas);
  assert.deepEqual(painted,['person-left']);assert.equal(resultA[0].bbox[0],.1);
  // The next video frame has moved, but pending inference must not replace the image.
  let release;
  const pending=pair.accept('jpeg-B',[{bbox:[.7,.2,.2,.3]}],()=>new Promise(r=>release=r));
  assert.equal(pair.paint(canvas)[0].bbox[0],.1);assert.equal(painted.at(-1),'person-left');
  release(imageB);await pending;
  assert.equal(pair.paint(canvas)[0].bbox[0],.7);assert.equal(painted.at(-1),'person-right');
  assert.equal(canvas.width,1280);assert.equal(canvas.height,720);
});
test('late decode after stopping a session never paints or leaks its bitmap',async()=>{
  const pair=new FramePair();let release,closed=false;
  const pending=pair.accept('old',[],()=>new Promise(r=>release=r));
  pair.reset();release({close(){closed=true}});
  assert.equal(await pending,false);assert.equal(pair.current,null);assert(closed);
});
