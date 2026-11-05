const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {wav16,analyse}=require('../web/mic-check.js');

test('WAV preserves rate, sample count, quiet levels and signed PCM',()=>{
  const samples=new Float32Array([0,1,-1,.001,NaN]);
  const data=new DataView(wav16(samples,16000));
  assert.equal(data.byteLength,54);
  assert.equal(data.getUint32(24,true),16000);
  assert.equal(data.getUint16(22,true),1);
  assert.equal(data.getUint32(40,true),10);
  assert.equal(data.getInt16(46,true),32767);
  assert.equal(data.getInt16(48,true),-32768);
  assert.equal(data.getInt16(50,true),33);
  assert.equal(data.getInt16(52,true),0);
});

test('quality distinguishes silence, clipping and brief speech followed by silence',()=>{
  assert.equal(analyse(new Float32Array(128000),16000).level,'quiet');
  assert.equal(analyse(new Float32Array(128000).fill(1),16000).level,'clipped');
  const samples=new Float32Array(128000);samples.fill(.05,0,1600);
  const report=analyse(samples,16000);
  assert.equal(report.level,'usable');assert.equal(report.seconds,8);
  assert.equal(report.peak,samples[0]);
});

test('probe captures exactly 8 seconds without emitting exam-session chunks',()=>{
  let Probe;const messages=[];
  vm.runInNewContext(fs.readFileSync('web/mic-probe-worklet.js','utf8'),{
    sampleRate:16000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:value=>messages.push(value)};}},
    registerProcessor:(name,Type)=>{assert.equal(name,'examwatch-mic-probe');Probe=Type;},
  });
  const probe=new Probe();const block=new Float32Array(128).fill(.025);
  for(let i=0;i<1000;i++)probe.process([[block]]);
  const complete=messages.filter(m=>m.samples);
  assert.equal(complete.length,1);assert.equal(complete[0].samples.length,128000);
  assert.equal(complete[0].rate,16000);
  assert(complete[0].samples.every(x=>x===block[0]));
  assert.equal(probe.process([[block]]),false);
  assert.equal(messages.filter(m=>m.samples).length,1);
  assert(messages.every(m=>m.start===undefined));
});
