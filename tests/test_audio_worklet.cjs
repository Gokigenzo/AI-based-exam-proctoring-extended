const vm=require('node:vm');const fs=require('node:fs');
const {test}=require('node:test');const assert=require('node:assert/strict');
function processor(){
  let Capture;const messages=[];
  const context={sampleRate:16000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:m=>{if(m.level===undefined)messages.push(m)}};}},registerProcessor:(name,Type)=>Capture=Type};
  vm.runInNewContext(fs.readFileSync('web/audio-worklet.js','utf8'),context);
  return {worklet:new Capture(),messages};
}
function feed(worklet,value,count){for(let i=0;i<count;i++)worklet.process([[new Float32Array(128).fill(value)]],[]);}
test('pauses emit a complete short utterance before maximum chunk duration',()=>{
  const {worklet,messages}=processor();
  feed(worklet,.05,200);feed(worklet,0,90);
  assert.equal(messages.length,1);assert(messages[0].samples.length/16000<3);
  assert.equal(messages[0].start,0);assert.equal(messages[0].rate,16000);
});
test('continuous speech is bounded to 8s and the final tail is flushed exactly once',()=>{
  const {worklet,messages}=processor();
  feed(worklet,.05,1100);
  assert.equal(messages.length,1);assert.equal(messages[0].samples.length,128000);
  worklet.port.onmessage({data:'flush'});
  assert.equal(messages.length,3);assert.equal(messages[1].start,8);assert(messages[2].done);
  feed(worklet,.05,2000);assert.equal(messages.length,3);
});
